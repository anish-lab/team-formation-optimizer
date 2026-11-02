"""Strict validation of request settings (never trust the client)."""
from __future__ import annotations
import json
import math
from graph.builder import ObjectiveConfig
from .errors import ApiError


def load_json_field(raw, name):
    if raw in (None, ""):
        raise ApiError("missing_field", f"'{name}' is required.", 400)
    try:
        return json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except json.JSONDecodeError:
        raise ApiError("invalid_json", f"'{name}' is not valid JSON.", 400)


def _num(d, key, default, lo, hi):
    v = d.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not (lo <= v <= hi):
        raise ApiError("invalid_setting", f"'{key}' must be a number in [{lo}, {hi}].", 422)
    return float(v)


def parse_settings(raw, max_time: float) -> dict:
    if not isinstance(raw, dict):
        raise ApiError("invalid_settings", "settings must be a JSON object.", 422)
    obj, team, lim = raw.get("objective") or {}, raw.get("team") or {}, raw.get("limits") or {}
    for name, d in (("objective", obj), ("team", team), ("limits", lim)):
        if not isinstance(d, dict):
            raise ApiError("invalid_settings", f"'{name}' must be an object.", 422)
    alpha, beta = _num(obj, "alpha", 1.0, 0, 1e6), _num(obj, "beta", 1.0, 0, 1e6)
    if alpha == 0 and beta == 0:
        raise ApiError("invalid_setting", "alpha and beta cannot both be zero.", 422)
    mode = obj.get("edge_mode", "hard")
    if mode not in ("hard", "soft"):
        raise ApiError("invalid_setting", "edge_mode must be 'hard' or 'soft'.", 422)
    pref = team.get("preferred_size", 4)
    if isinstance(pref, bool) or not isinstance(pref, int) or not (1 <= pref <= 50):
        raise ApiError("invalid_setting", "preferred_size must be an integer in [1, 50].", 422)
    objective = ObjectiveConfig(alpha, beta, mode, _num(obj, "threshold", 0.5, 0, 1), pref)
    nl = lim.get("node_limit")
    if nl is not None and (isinstance(nl, bool) or not isinstance(nl, int) or nl < 1):
        raise ApiError("invalid_setting", "node_limit must be a positive integer.", 422)
    return {"objective": objective, "team": dict(team, preferred_size=pref),
            "limits": {"time_limit": _num(lim, "time_limit", 30, 0.1, max_time), "node_limit": nl,
                       "max_cliques": int(_num(lim, "max_cliques", 250000, 100, 2_000_000)),
                       "use_coloring": bool(lim.get("use_coloring", True)),
                       "allow_heuristic": bool(lim.get("allow_heuristic", False))}}
