import io
import json
import time
import pytest
from app import create_app

ROWS = ["id,skill,dept,py"] + [f"c{i},{(i * 7) % 10},{'ab'[i % 2]},{i % 2}" for i in range(12)]
CSV = "\n".join(ROWS)
SCHEMA = [{"name": "skill", "type": "numeric_integer", "role": "both", "importance": 2},
          {"name": "dept", "type": "categorical", "role": "compat"},
          {"name": "py", "type": "binary", "role": "value"}]
SETTINGS = {"objective": {"alpha": 1, "beta": 1, "edge_mode": "soft"},
            "team": {"policy": "variable_sizes", "preferred_size": 3, "min_size": 3, "max_size": 4, "num_teams": 3, "strict_team_count": True},
            "limits": {"time_limit": 20}}


@pytest.fixture()
def client():
    return create_app({"TESTING": True}).test_client()


def form(csv=CSV, schema=SCHEMA, settings=SETTINGS, name="d.csv", idc="id"):
    return {"file": (io.BytesIO(csv.encode()), name), "schema": json.dumps(schema), "id_column": idc, "settings": json.dumps(settings)}


def wait(client, tid):
    for _ in range(200):
        s = client.get(f"/api/optimization/{tid}").get_json()
        if s["status"] not in ("queued", "running"):
            return s
        time.sleep(0.05)
    raise AssertionError("timeout")


def test_health(client):
    assert client.get("/api/health").get_json()["ok"]


def test_full_flow_upload_validate_optimize_results_export(client):
    r = client.post("/api/validate-csv", data=form(), content_type="multipart/form-data")
    assert r.get_json()["report"]["ok"]
    r = client.post("/api/build-graph", data=form(), content_type="multipart/form-data")
    assert r.get_json()["metrics"]["vertices"] == 12
    r = client.post("/api/optimize", data=form(), content_type="multipart/form-data")
    assert r.status_code == 202
    tid = r.get_json()["task_id"]
    assert wait(client, tid)["status"] == "finished"
    res = client.get(f"/api/optimization/{tid}/results").get_json()["result"]
    assert res["status"] == "optimal" and res["optimality_proven"]
    ids = [m["id"] for t in res["teams"] for m in t["members"]]
    assert len(ids) == len(set(ids)) and len(res["teams"]) == 3 and all(t["satisfies_hard_constraints"] for t in res["teams"])
    assert res["summary"]["assigned"] + res["summary"]["unassigned"] == 12
    assert client.get(f"/api/optimization/{tid}/statistics").get_json()["stats"]["nodes"] >= 0
    csv_out = client.get(f"/api/optimization/{tid}/export?format=teams_csv").data.decode()
    assert csv_out.startswith("team,candidate_id") and len(csv_out.strip().splitlines()) == len(ids) + 1
    js = json.loads(client.get(f"/api/optimization/{tid}/export?format=json").data)
    assert "configuration" in js and js["configuration"]["features"][0]["name"] == "skill"
    assert b"PROVEN OPTIMUM" in client.get(f"/api/optimization/{tid}/export?format=summary_txt").data
    assert client.get(f"/api/optimization/{tid}/export?format=bogus").status_code == 400


def test_validation_errors_are_structured(client):
    bad = CSV + "\nc1,3,a,1\nc99,x,a,1"
    r = client.post("/api/optimize", data=form(csv=bad), content_type="multipart/form-data")
    j = r.get_json()
    assert r.status_code == 422 and j["error"]["code"] == "validation_failed"
    assert {e["code"] for e in j["error"]["details"]["errors"]} >= {"duplicate_id", "invalid_value"}


def test_infeasible_configuration_returns_suggestions(client):
    s = json.loads(json.dumps(SETTINGS))
    s["team"] = {"policy": "full_coverage", "preferred_size": 4, "min_size": 4, "max_size": 4, "num_teams": 2}
    r = client.post("/api/optimize", data=form(settings=s), content_type="multipart/form-data")
    j = r.get_json()
    assert r.status_code == 422 and j["error"]["code"] == "infeasible_configuration" and j["error"]["details"][0]["suggestions"]


def test_bad_requests(client):
    assert client.post("/api/optimize", data={}, content_type="multipart/form-data").status_code == 400
    assert client.post("/api/optimize", data=form(name="x.exe"), content_type="multipart/form-data").status_code == 422
    assert client.post("/api/optimize", data=form(schema=[{"name": "a", "type": "nope"}]), content_type="multipart/form-data").status_code == 422
    s = {"objective": {"alpha": 0, "beta": 0}}
    assert client.post("/api/optimize", data=form(settings=s), content_type="multipart/form-data").status_code == 422
    assert client.get("/api/optimization/nope").status_code == 404
    assert client.post("/api/validate-configuration", json={"n_candidates": 50, "team": {"policy": "strict_equal", "preferred_size": 4}}).get_json()["valid"]
    assert client.post("/api/validate-configuration", json={"n_candidates": 3, "team": {"policy": "strict_equal", "preferred_size": 4}}).get_json()["valid"] is False


def test_evaluate_endpoint_compares_modes(client):
    s = json.loads(json.dumps(SETTINGS))
    r = client.post("/api/evaluate", data={**form(settings=s), "repeats": "1"}, content_type="multipart/form-data")
    rows = r.get_json()["evaluation"]["rows"]
    assert [x["algorithm"] for x in rows] == ["BBMCW (full algorithm)", "BBMCW without MCOVER", "BBMCW without COVER and MCOVER", "BBMCW without AMTS"]
    assert max(x["objective"] for x in rows) - min(x["objective"] for x in rows) < 1e-9


def test_evaluate_includes_paper_style_comparison(client):
    r = client.post("/api/evaluate", data={**form(), "repeats": "1"}, content_type="multipart/form-data")
    vw = r.get_json()["evaluation"]["vertex_weighted"]["rows"]
    assert len(vw) == 4
    assert max(x["objective"] for x in vw) - min(x["objective"] for x in vw) < 1e-9
