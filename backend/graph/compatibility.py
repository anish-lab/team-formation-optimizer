"""Feature-level formulas (all scores are in [0,1]).

value_score:  numeric -> (x-lo)/(hi-lo) (or 1-that for lower_better); binary -> 0/1;
              categorical -> user supplied category_values[x].
pair_score:   numeric similarity = 1 - min(1,|a-b|/(hi-lo)); complementarity = min(1,|a-b|/(hi-lo))
              categorical/binary similarity = 1 if equal else 0; complementarity = 1 if different else 0
              categorical 'matrix' = user supplied compat_matrix["a|b"] (symmetric lookup).
"""
from __future__ import annotations
from data.feature_schema import FeatureDef


def value_score(f: FeatureDef, x, st: dict) -> float:
    if f.ftype == "binary":
        return float(x)
    if f.ftype == "categorical":
        return float(f.category_values[x])
    lo, hi = st["min"], st["max"]
    s = 0.0 if hi <= lo else min(1.0, max(0.0, (x - lo) / (hi - lo)))
    return 1.0 - s if f.direction == "lower_better" else s


def matrix_lookup(f: FeatureDef, a: str, b: str) -> float:
    m = f.compat_matrix or {}
    for key in (f"{a}|{b}", f"{b}|{a}"):
        if key in m:
            return float(m[key])
    raise ValueError(f"compat_matrix of '{f.name}' has no entry for '{a}|{b}'")


def pair_score(f: FeatureDef, a, b, st: dict) -> float:
    if f.is_numeric:
        lo, hi = st["min"], st["max"]
        d = 0.0 if hi <= lo else min(1.0, abs(a - b) / (hi - lo))
        return d if f.compat_method == "complementarity" else 1.0 - d
    if f.compat_method == "matrix":
        return matrix_lookup(f, a, b)
    eq = a == b
    if f.compat_method == "complementarity":
        return 0.0 if eq else 1.0
    return 1.0 if eq else 0.0
