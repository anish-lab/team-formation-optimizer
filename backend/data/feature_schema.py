"""User-defined feature schema (no hard-coded features)."""
from __future__ import annotations
import math
from dataclasses import dataclass, field

FEATURE_TYPES = ("numeric_continuous", "numeric_integer", "categorical", "binary")
ROLES = ("value", "compat", "both", "none")
METHODS = ("similarity", "complementarity", "matrix")
MISSING = ("error", "impute_mean", "impute_median", "impute_mode", "fill_value")


class SchemaError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class FeatureDef:
    name: str
    column: str
    ftype: str
    importance: float = 1.0
    required: bool = True
    role: str = "both"                 # contributes to candidate value, pairwise compatibility, both, or neither
    compat_method: str = "similarity"  # similarity | complementarity | matrix (categorical only)
    direction: str = "higher_better"   # numeric/binary value direction
    min_value: float | None = None
    max_value: float | None = None
    categories: list[str] | None = None
    category_values: dict[str, float] | None = None   # categorical -> value score in [0,1] (required for value role)
    compat_matrix: dict[str, float] | None = None     # "a|b" -> compatibility in [0,1]
    missing_policy: str = "error"
    fill_value: str | None = None

    @property
    def is_numeric(self) -> bool:
        return self.ftype in ("numeric_continuous", "numeric_integer")

    @property
    def uses_value(self) -> bool:
        return self.role in ("value", "both") and self.importance > 0

    @property
    def uses_compat(self) -> bool:
        return self.role in ("compat", "both") and self.importance > 0

    def to_dict(self) -> dict:
        return {"name": self.name, "column": self.column, "type": self.ftype, "importance": self.importance,
                "required": self.required, "role": self.role, "compat_method": self.compat_method,
                "direction": self.direction, "min": self.min_value, "max": self.max_value,
                "categories": self.categories, "category_values": self.category_values,
                "compat_matrix": self.compat_matrix, "missing_policy": self.missing_policy,
                "fill_value": self.fill_value}


def _num(x, label, errs, lo=None):
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        errs.append(f"{label} must be a number")
        return None
    if not math.isfinite(v) or (lo is not None and v < lo):
        errs.append(f"{label} must be a finite number" + (f" >= {lo}" if lo is not None else ""))
        return None
    return v


def parse_features(raw) -> list[FeatureDef]:
    errs: list[str] = []
    if not isinstance(raw, list) or not raw:
        raise SchemaError(["Feature schema must be a non-empty list of features"])
    feats, names = [], set()
    for k, r in enumerate(raw):
        if not isinstance(r, dict):
            errs.append(f"feature #{k + 1}: must be an object")
            continue
        name = str(r.get("name", "")).strip()
        lab = f"feature '{name or k + 1}'"
        if not name:
            errs.append(f"feature #{k + 1}: name is required")
            continue
        if name in names:
            errs.append(f"{lab}: duplicate feature name")
        names.add(name)
        ftype = r.get("type")
        if ftype not in FEATURE_TYPES:
            errs.append(f"{lab}: type must be one of {FEATURE_TYPES}")
            continue
        imp = _num(r.get("importance", 1.0), f"{lab} importance", errs, 0.0)
        role = r.get("role", "both")
        if role not in ROLES:
            errs.append(f"{lab}: role must be one of {ROLES}")
        method = r.get("compat_method", "similarity")
        if method not in METHODS:
            errs.append(f"{lab}: compat_method must be one of {METHODS}")
        if r.get("direction", "higher_better") not in ("higher_better", "lower_better"):
            errs.append(f"{lab}: direction must be higher_better or lower_better")
        mp = r.get("missing_policy", "error")
        if mp not in MISSING:
            errs.append(f"{lab}: missing_policy must be one of {MISSING}")
        if mp in ("impute_mean", "impute_median") and ftype not in ("numeric_continuous", "numeric_integer"):
            errs.append(f"{lab}: {mp} only applies to numeric features")
        if mp == "impute_mode" and ftype not in ("categorical", "binary"):
            errs.append(f"{lab}: impute_mode only applies to categorical/binary features")
        if mp == "fill_value" and r.get("fill_value") in (None, ""):
            errs.append(f"{lab}: fill_value policy needs a fill_value")
        lo, hi = _num(r.get("min"), f"{lab} min", errs), _num(r.get("max"), f"{lab} max", errs)
        if lo is not None and hi is not None and lo >= hi:
            errs.append(f"{lab}: min must be smaller than max")
        cats = r.get("categories")
        if cats is not None and (not isinstance(cats, list) or not all(isinstance(c, str) for c in cats)):
            errs.append(f"{lab}: categories must be a list of strings")
            cats = None
        cv, cm = r.get("category_values"), r.get("compat_matrix")
        for label, d in (("category_values", cv), ("compat_matrix", cm)):
            if d is not None:
                if not isinstance(d, dict) or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in d.values()):
                    errs.append(f"{lab}: {label} must map names to numbers in [0,1]")
        if method == "matrix" and role in ("compat", "both") and (ftype != "categorical" or not cm):
            errs.append(f"{lab}: 'matrix' compatibility needs a categorical feature and a compat_matrix")
        if ftype == "categorical" and role in ("value", "both") and (imp or 0) > 0 and not cv:
            errs.append(f"{lab}: categorical features used for candidate value need explicit category_values "
                        f"(no arbitrary scores are invented); set role to 'compat' or 'none' otherwise")
        feats.append(FeatureDef(name, str(r.get("column") or name).strip(), ftype, imp if imp is not None else 1.0,
                                bool(r.get("required", True)), role, method, r.get("direction", "higher_better"),
                                lo, hi, cats, cv, cm, mp, None if r.get("fill_value") is None else str(r["fill_value"])))
    if errs:
        raise SchemaError(errs)
    return feats
