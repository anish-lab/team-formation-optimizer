"""Dataset validation against a user-defined schema. Nothing is silently dropped or invented."""
from __future__ import annotations
import math
import statistics
from collections import Counter
from dataclasses import dataclass, field
import pandas as pd
from .csv_loader import is_missing
from .feature_schema import FeatureDef

TRUE = {"true", "t", "yes", "y", "1"}
FALSE = {"false", "f", "no", "n", "0"}
MAX_ERRORS = 200


@dataclass
class ParsedTable:
    ids: list[str]
    values: dict[str, list]
    stats: dict[str, dict]
    features: list[FeatureDef]
    id_generated: bool = False


def _parse(f: FeatureDef, s: str):
    s = str(s).strip()
    if f.is_numeric:
        x = float(s)
        if not math.isfinite(x):
            raise ValueError("non-finite number")
        if f.ftype == "numeric_integer" and x != int(x):
            raise ValueError("not an integer")
        return x
    if f.ftype == "binary":
        if s.lower() in TRUE:
            return 1.0
        if s.lower() in FALSE:
            return 0.0
        raise ValueError("not a boolean (use true/false, yes/no, 1/0)")
    return s


def inspect_columns(df: pd.DataFrame) -> list[dict]:
    """Per-column inspection used for schema suggestions."""
    out = []
    for c in df.columns:
        vals = [v for v in df[c] if not is_missing(v)]
        numeric = bool(vals)
        integer = bool(vals)
        for v in vals:
            try:
                x = float(v)
                integer = integer and math.isfinite(x) and x == int(x)
            except ValueError:
                numeric = integer = False
                break
        lower = {v.strip().lower() for v in vals}
        sug = ("binary" if lower and lower <= (TRUE | FALSE) and len(lower) <= 2 else
               "numeric_integer" if integer else "numeric_continuous" if numeric else "categorical")
        out.append({"name": c, "missing": len(df) - len(vals), "unique": len(set(vals)), "suggested_type": sug})
    return out


def validate_dataset(df: pd.DataFrame, features: list[FeatureDef], id_column: str | None):
    errors: list[dict] = []
    warnings: list[dict] = []
    n_err = [0]

    def err(row, col, code, msg):
        n_err[0] += 1
        if len(errors) < MAX_ERRORS:
            errors.append({"row": row, "column": col, "code": code, "message": msg})

    def warn(col, code, msg):
        warnings.append({"column": col, "code": code, "message": msg})

    n = len(df)
    id_generated = False
    if id_column:
        if id_column not in df.columns:
            err(None, id_column, "missing_id_column", f"ID column '{id_column}' not found in the file.")
            ids = [f"row-{i + 1}" for i in range(n)]
        else:
            ids = [str(v).strip() for v in df[id_column]]
            for i, v in enumerate(ids):
                if v == "":
                    err(i + 1, id_column, "blank_id", "Candidate ID is blank.")
            for v, k in Counter(ids).items():
                if v and k > 1:
                    rows = [i + 1 for i, x in enumerate(ids) if x == v]
                    err(rows[0], id_column, "duplicate_id", f"Candidate ID '{v}' appears {k} times (rows {rows[:6]}).")
    else:
        ids = [f"row-{i + 1}" for i in range(n)]
        id_generated = True
        warn(None, "generated_ids", "No ID column selected: IDs were generated from row numbers and are only valid for this upload.")

    values, stats, used = {}, {}, []
    for f in features:
        if id_column and f.column == id_column:
            warn(f.column, "id_as_feature", f"ID column '{f.column}' is also used as feature '{f.name}'.")
        if f.column not in df.columns:
            if f.required:
                err(None, f.column, "missing_column", f"Required column '{f.column}' (feature '{f.name}') not found.")
            else:
                warn(f.column, "feature_skipped", f"Optional feature '{f.name}' skipped: column '{f.column}' not found.")
            continue
        parsed, miss = [], []
        for i, raw in enumerate(df[f.column]):
            if is_missing(raw):
                parsed.append(None)
                miss.append(i)
                continue
            try:
                parsed.append(_parse(f, raw))
            except ValueError as e:
                parsed.append(None)
                err(i + 1, f.column, "invalid_value", f"'{raw}' is invalid for {f.ftype}: {e}.")
        bad_cells = {e["row"] for e in errors if e["column"] == f.column and e["code"] == "invalid_value"}
        present = [p for p in parsed if p is not None]
        if miss:
            if f.missing_policy == "error":
                for i in miss:
                    err(i + 1, f.column, "missing_value", f"Missing value for feature '{f.name}' (policy: reject).")
            elif not present:
                err(None, f.column, "all_missing", f"Column '{f.column}' has no usable values to impute from.")
            else:
                try:
                    if f.missing_policy == "impute_mean":
                        fill = statistics.fmean(present)
                    elif f.missing_policy == "impute_median":
                        fill = statistics.median(present)
                    elif f.missing_policy == "impute_mode":
                        fill = Counter(present).most_common(1)[0][0]
                    else:
                        fill = _parse(f, f.fill_value)
                    for i in miss:
                        parsed[i] = fill
                    warn(f.column, "imputed", f"{len(miss)} missing value(s) in '{f.name}' replaced by {f.missing_policy.replace('_', ' ')} = {fill!r}; "
                         "this treats those candidates as if they had that value in scoring.")
                except ValueError as e:
                    err(None, f.column, "invalid_fill", f"fill_value for '{f.name}' is invalid: {e}.")
        if f.is_numeric:
            for i, p in enumerate(parsed):
                if p is None:
                    continue
                if (f.min_value is not None and p < f.min_value) or (f.max_value is not None and p > f.max_value):
                    err(i + 1, f.column, "out_of_range", f"{p:g} outside the configured range [{f.min_value}, {f.max_value}].")
        if f.ftype == "categorical":
            known = set(f.categories or [])
            for i, p in enumerate(parsed):
                if p is not None and f.categories and p not in known:
                    err(i + 1, f.column, "unknown_category", f"'{p}' is not one of the declared categories {sorted(known)}.")
                if p is not None and f.category_values and p not in f.category_values:
                    err(i + 1, f.column, "no_category_value", f"No candidate-value score defined for category '{p}'.")
        vals = [p for p in parsed if p is not None]
        if f.is_numeric and vals:
            lo = f.min_value if f.min_value is not None else min(vals)
            hi = f.max_value if f.max_value is not None else max(vals)
            if hi <= lo:
                warn(f.column, "constant_feature", f"Feature '{f.name}' has a single value; it carries no information.")
            stats[f.name] = {"min": lo, "max": hi}
        elif f.ftype == "categorical":
            stats[f.name] = {"categories": sorted(set(f.categories or []) | set(vals))}
        else:
            stats[f.name] = {}
        values[f.name] = parsed
        used.append(f)

    preview = df.head(10).to_dict("records")
    report = {"ok": n_err[0] == 0, "n_rows": n, "n_columns": len(df.columns), "columns": list(df.columns),
              "id_column": id_column, "id_generated": id_generated, "errors": errors,
              "error_count": n_err[0], "errors_truncated": n_err[0] > len(errors),
              "warnings": warnings, "preview": preview, "features_used": [f.name for f in used]}
    table = ParsedTable(ids, values, stats, used, id_generated) if report["ok"] else None
    return report, table
