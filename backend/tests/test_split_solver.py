import io
import json
import random
import time
from math import comb
import pytest
from app import create_app
from optimization.constraints import TeamConstraints, resolve_constraints, validate_assignment
from optimization.models import Graph
from optimization.split_solver import can_split, solve_by_splitting
from optimization.team_conflict_solver import solve_teams_bbmcw


def complete_graph(n, k, seed=0):
    r = random.Random(seed)
    ew = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            ew[i][j] = ew[j][i] = r.random() / comb(k, 2)
    return Graph(ids=[f"p{i}" for i in range(n)], vw=[r.random() / k for _ in range(n)], ew=ew,
                 adj=[((1 << n) - 1) & ~(1 << i) for i in range(n)])


def equal(s, t):
    return TeamConstraints(s, s, t, t, False, True, s, None, "coverage_first", "strict_equal")


def test_forty_people_in_teams_of_five_are_all_placed():
    g, tc = complete_graph(40, 5), equal(5, 8)
    assert can_split(g, tc)
    r = solve_by_splitting(g, tc, 1.0)
    assert not validate_assignment(g, tc, [t.members for t in r.teams])
    assert len(r.teams) == 8 and r.coverage == 40 and not r.unassigned


def test_never_reported_as_proven_and_better_than_the_starting_split():
    g, tc = complete_graph(40, 5), equal(5, 8)
    start = solve_by_splitting(g, tc, 0.0)
    r = solve_by_splitting(g, tc, 1.0)
    assert r.status == "feasible_not_proven" and not r.optimality_proven
    assert r.total_score > start.total_score


def test_leftovers_are_listed_and_can_join_a_team():
    g, tc = complete_graph(43, 5), equal(5, 8)
    r = solve_by_splitting(g, tc, 1.0)
    assert r.coverage == 40 and len(r.unassigned) == 3
    assert not set(r.unassigned) & {v for t in r.teams for v in t.members}
    assert not validate_assignment(g, tc, [t.members for t in r.teams])


def test_everyone_in_a_team_with_sizes_differing_by_one():
    n, s = 42, 5
    tc = resolve_constraints(n, {"policy": "full_coverage", "preferred_size": s, "min_size": s, "max_size": s + 1, "full_coverage": True})
    g = complete_graph(n, s)
    assert can_split(g, tc)
    r = solve_by_splitting(g, tc, 1.0)
    assert r.coverage == n and not validate_assignment(g, tc, [t.members for t in r.teams])
    assert {len(t.members) for t in r.teams} <= {s, s + 1}


@pytest.mark.parametrize("seed", range(5))
def test_never_beats_the_proven_best_and_usually_reaches_it(seed):
    g, tc = complete_graph(12, 3, seed), equal(3, 4)
    best = solve_teams_bbmcw(g, tc, 30)
    assert best.optimality_proven
    r = solve_by_splitting(g, tc, 5.0)
    assert r.total_score <= best.total_score + 1e-7
    assert r.total_score >= 0.97 * best.total_score


def test_small_groups_and_restricted_graphs_are_not_split():
    assert not can_split(complete_graph(15, 3), equal(3, 5))
    g = complete_graph(40, 5)
    g.adj[0] &= ~(1 << 1)
    g.adj[1] &= ~1
    assert not can_split(g, equal(5, 8))


def test_very_large_teams_are_not_split():
    assert not can_split(complete_graph(40, 9), equal(9, 4))


def test_stops_when_asked():
    g, tc = complete_graph(40, 5), equal(5, 8)
    t0 = time.perf_counter()
    r = solve_by_splitting(g, tc, 30.0, should_stop=lambda: time.perf_counter() - t0 > 0.2)
    assert time.perf_counter() - t0 < 5.0 and r.coverage == 40


def test_website_flow_with_forty_people():
    client = create_app({"TESTING": True}).test_client()
    rows = ["id,skill,dept"] + [f"s{i},{(i * 37) % 61},{'abcd'[i % 4]}" for i in range(40)]
    schema = [{"name": "skill", "type": "numeric_integer", "role": "value", "importance": 3},
              {"name": "dept", "type": "categorical", "role": "compat", "compat_method": "complementarity", "importance": 3}]
    settings = {"objective": {"alpha": 1, "beta": 1, "edge_mode": "soft", "threshold": 0.5},
                "team": {"policy": "leave_unassigned", "preferred_size": 5, "strict_team_count": True, "strict_team_size": True,
                         "equal_sizes": True, "priority": "coverage_first"},
                "limits": {"time_limit": 1, "max_cliques": 250000}}
    data = {"file": (io.BytesIO("\n".join(rows).encode()), "s.csv"), "schema": json.dumps(schema), "id_column": "id", "settings": json.dumps(settings)}
    r = client.post("/api/optimize", data=data, content_type="multipart/form-data")
    assert r.status_code == 202
    tid = r.get_json()["task_id"]
    for _ in range(200):
        if client.get(f"/api/optimization/{tid}").get_json()["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    res = client.get(f"/api/optimization/{tid}/results").get_json()["result"]
    assert res["status"] == "feasible_not_proven" and not res["optimality_proven"]
    ids = [m for t in res["teams"] for m in t["members"]]
    assert len(res["teams"]) == 8 and len(ids) == 40 and len(set(ids)) == 40 and not res["unassigned"]
