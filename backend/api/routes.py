"""Flask HTTP API.  Every endpoint validates its input again on the server."""
from __future__ import annotations
import json
import threading
from flask import Blueprint, current_app, jsonify, request, Response
from data.csv_loader import read_csv_bytes, CsvError
from data.feature_schema import parse_features, SchemaError
from data.validation import validate_dataset, inspect_columns
from graph.builder import build_graph
from graph.metrics import graph_metrics
from optimization.constraints import resolve_constraints, check_feasibility, ConstraintError
from evaluation.benchmark import run_comparison, BRUTE_FORCE_MAX_N
from evaluation.reports import teams_csv, unassigned_csv, summary_text
from .errors import ApiError
from .schemas import load_json_field, parse_settings
from .tasks import Task

bp = Blueprint("api", __name__, url_prefix="/api")


def ok(**kw):
    return jsonify({"ok": True, **kw})


def _df():
    f = request.files.get("file")
    if f is None:
        raise ApiError("missing_file", "Upload a CSV file in the 'file' form field.", 400)
    cfg = current_app.config
    try:
        return read_csv_bytes(f.filename, f.read(cfg["MAX_UPLOAD_BYTES"] + 1), cfg["MAX_UPLOAD_BYTES"], cfg["MAX_ROWS"])
    except CsvError as e:
        raise ApiError(e.code, e.message, 422, e.details)


def _features():
    try:
        return parse_features(load_json_field(request.form.get("schema"), "schema"))
    except SchemaError as e:
        raise ApiError("invalid_schema", "The feature schema is invalid.", 422, e.errors)


def _prepare():
    df = _df()
    feats = _features()
    idc = (request.form.get("id_column") or "").strip() or None
    report, table = validate_dataset(df, feats, idc)
    if not report["ok"]:
        raise ApiError("validation_failed", "The dataset has validation errors.", 422, report)
    if table and len(table.ids) > current_app.config["MAX_CANDIDATES"]:
        raise ApiError("too_many_candidates", f"At most {current_app.config['MAX_CANDIDATES']} candidates are supported.", 422)
    settings = parse_settings(load_json_field(request.form.get("settings", "{}"), "settings"), current_app.config["MAX_TIME_LIMIT"])
    try:
        built = build_graph(table, settings["objective"])
        tc = resolve_constraints(len(table.ids), settings["team"])
    except ValueError as e:
        raise ApiError("graph_error", str(e), 422)
    except ConstraintError as e:
        raise ApiError("invalid_team_settings", "Team settings are invalid.", 422, e.issues)
    return built, tc, settings, feats, report


@bp.get("/health")
def health():
    return ok(status="up")


@bp.post("/preview-data")
def preview_data():
    df = _df()
    return ok(n_rows=len(df), n_columns=len(df.columns), columns=inspect_columns(df), preview=df.head(10).to_dict("records"))


@bp.post("/validate-csv")
def validate_csv():
    df = _df()
    feats = _features() if request.form.get("schema") else []
    idc = (request.form.get("id_column") or "").strip() or None
    report, _ = validate_dataset(df, feats, idc)
    return ok(report=report)


@bp.post("/validate-configuration")
def validate_configuration():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("invalid_json", "JSON body required.", 400)
    n = body.get("n_candidates")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ApiError("invalid_setting", "n_candidates must be a positive integer.", 422)
    if "features" in body:
        try:
            parse_features(body["features"])
        except SchemaError as e:
            raise ApiError("invalid_schema", "The feature schema is invalid.", 422, e.errors)
    try:
        tc = resolve_constraints(n, body.get("team") or {})
    except ConstraintError as e:
        return ok(valid=False, issues=e.issues)
    issues = check_feasibility(n, tc)
    return ok(valid=not issues, issues=issues, constraints=tc.to_dict())


@bp.post("/build-graph")
def build_graph_ep():
    built, tc, settings, feats, report = _prepare()
    out = {"metrics": graph_metrics(built.graph), "warnings": built.warnings, "constraints": tc.to_dict(),
           "feasibility_issues": check_feasibility(built.graph.n, tc)}
    pair = request.form.get("explain_pair")
    if pair:
        a, b = (x.strip() for x in pair.split(",", 1))
        if a not in built.graph.ids or b not in built.graph.ids or a == b:
            raise ApiError("invalid_pair", "Unknown candidate IDs for explain_pair.", 422)
        out["pair"] = built.explain_pair(built.graph.ids.index(a), built.graph.ids.index(b))
    return ok(**out, warnings_data=report["warnings"])


@bp.post("/optimize")
def optimize():
    built, tc, settings, feats, report = _prepare()
    issues = check_feasibility(built.graph.n, tc)
    if issues:
        raise ApiError("infeasible_configuration", "The team settings cannot be satisfied.", 422, issues)
    config = {"features": [f.to_dict() for f in feats], "objective": settings["objective"].to_dict(),
              "team_settings": settings["team"], "resolved_constraints": tc.to_dict(), "limits": settings["limits"],
              "id_column": request.form.get("id_column") or None, "n_candidates": built.graph.n}
    task = Task(built, tc, settings["limits"], config)
    current_app.extensions["tasks"].add(task)
    threading.Thread(target=task.run, daemon=True).start()
    return jsonify({"ok": True, "task_id": task.id}), 202


def _task(tid):
    t = current_app.extensions["tasks"].get(tid)
    if t is None:
        raise ApiError("task_not_found", "Unknown task id.", 404)
    return t


@bp.get("/optimization/<tid>")
def task_status(tid):
    return ok(**_task(tid).public())


@bp.get("/optimization/<tid>/results")
def task_results(tid):
    t = _task(tid)
    if t.status in ("queued", "running"):
        raise ApiError("not_ready", "The optimisation is still running.", 409)
    if t.status == "failed":
        raise ApiError(t.error["code"], t.error["message"], 500)
    return ok(result=t.result, config=t.config)


@bp.get("/optimization/<tid>/statistics")
def task_stats(tid):
    t = _task(tid)
    if t.result is None:
        raise ApiError("not_ready", "No statistics yet.", 409)
    return ok(stats=t.result["stats"], graph_metrics=t.result["graph_metrics"], status=t.result["status"])


@bp.post("/optimization/<tid>/cancel")
def task_cancel(tid):
    t = _task(tid)
    t.cancel.set()
    return ok(status="cancel_requested")


@bp.get("/optimization/<tid>/export")
def task_export(tid):
    t = _task(tid)
    if t.result is None:
        raise ApiError("not_ready", "Nothing to export yet.", 409)
    fmt = request.args.get("format", "json")
    r = t.result
    if fmt == "teams_csv":
        return Response(teams_csv(r), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=teams.csv"})
    if fmt == "unassigned_csv":
        return Response(unassigned_csv(r), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=unassigned.csv"})
    if fmt == "stats_json":
        body = json.dumps({"stats": r["stats"], "graph_metrics": r["graph_metrics"], "status": r["status"],
                           "optimality_proven": r["optimality_proven"], "termination_reason": r["termination_reason"]}, indent=2)
        return Response(body, mimetype="application/json", headers={"Content-Disposition": "attachment; filename=statistics.json"})
    if fmt == "summary_txt":
        return Response(summary_text(r, t.config), mimetype="text/plain", headers={"Content-Disposition": "attachment; filename=summary.txt"})
    if fmt == "json":
        slim = {k: r[k] for k in ("status", "optimality_proven", "heuristic", "termination_reason", "objective", "constraints", "summary", "unassigned", "stats")}
        slim["teams"] = [{"team": x["team"], "score": x["score"], "value_score": x["value_score"], "compat_score": x["compat_score"],
                          "members": [m["id"] for m in x["members"]]} for x in r["teams"]]
        return Response(json.dumps({"result": slim, "configuration": t.config}, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": "attachment; filename=team_assignment.json"})
    raise ApiError("invalid_format", "format must be teams_csv, unassigned_csv, json, stats_json or summary_txt.", 400)


@bp.post("/evaluate")
def evaluate():
    built, tc, settings, feats, report = _prepare()
    issues = check_feasibility(built.graph.n, tc)
    if issues:
        raise ApiError("infeasible_configuration", "The team settings cannot be satisfied.", 422, issues)
    try:
        repeats = int(request.form.get("repeats", 3))
    except ValueError:
        raise ApiError("invalid_setting", "repeats must be an integer.", 422)
    L = settings["limits"]
    out = run_comparison(built.graph, tc, min(L["time_limit"], 60.0), L["node_limit"], L["max_cliques"], max(1, min(repeats, 5)))
    return ok(evaluation=out, brute_force_max_n=BRUTE_FORCE_MAX_N)
