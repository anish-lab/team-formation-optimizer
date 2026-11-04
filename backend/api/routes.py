"""Flask HTTP API.  Every endpoint validates its input again on the server."""
from __future__ import annotations
import threading
from flask import Blueprint, current_app, jsonify, request
from data.csv_loader import read_csv_bytes, CsvError
from data.feature_schema import parse_features, SchemaError
from data.validation import validate_dataset, inspect_columns
from graph.builder import build_graph
from optimization.constraints import resolve_constraints, check_feasibility, ConstraintError
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
    return built, tc, settings


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


@bp.post("/optimize")
def optimize():
    built, tc, settings = _prepare()
    issues = check_feasibility(built.graph.n, tc)
    if issues:
        raise ApiError("infeasible_configuration", "The team settings cannot be satisfied.", 422, issues)
    task = Task(built, tc, settings["limits"])
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
    return ok(result=t.result)


@bp.post("/optimization/<tid>/cancel")
def task_cancel(tid):
    t = _task(tid)
    t.cancel.set()
    return ok(status="cancel_requested")
