import pytest
from data.csv_loader import read_csv_bytes, CsvError
from data.feature_schema import parse_features, SchemaError
from data.validation import validate_dataset

MB = 1_000_000


def load(text, name="a.csv", max_bytes=MB):
    return read_csv_bytes(name, text.encode(), max_bytes)


def feats(*specs):
    return parse_features(list(specs))


SK = {"name": "skill", "type": "numeric_continuous", "importance": 2}
DEPT = {"name": "dept", "type": "categorical", "role": "compat"}


def test_rejects_bad_files():
    for args, code in [(("a.exe", b"a,b\n1,2"), "invalid_file_type"), (("a.csv", b"  "), "empty_file"),
                       (("a.csv", b"a,a\n1,2"), "duplicate_columns"), (("a.csv", b"a,,c\n1,2,3"), "invalid_header"),
                       (("a.csv", b"a,b\n"), "no_rows"), (("a.csv", b"\xff\xfe\x00"), "invalid_encoding"),
                       (("../../etc/a.csv", b"x" * 50), "file_too_large")]:
        with pytest.raises(CsvError) as e:
            read_csv_bytes(*args, 10 if code == "file_too_large" else MB)
        assert e.value.code == code


def test_valid_dataset_with_generated_ids_warns():
    df = load("skill,dept\n1,a\n2,b\n")
    rep, table = validate_dataset(df, feats(SK, DEPT), None)
    assert rep["ok"] and rep["id_generated"] and any(w["code"] == "generated_ids" for w in rep["warnings"])
    assert table.ids == ["row-1", "row-2"]


def test_reports_row_and_column_problems():
    df = load("id,skill,dept\nx,1,a\nx,abc,b\ny,,c\n")
    rep, table = validate_dataset(df, feats(SK, DEPT), "id")
    codes = {(e["code"], e["column"]) for e in rep["errors"]}
    assert not rep["ok"] and table is None
    assert ("duplicate_id", "id") in codes and ("invalid_value", "skill") in codes and ("missing_value", "skill") in codes
    assert any(e["row"] == 2 for e in rep["errors"])


def test_missing_policy_imputes_with_warning_and_never_silently():
    df = load("id,skill,dept\na,1,x\nb,,y\nc,3,x\n")
    f = feats({**SK, "missing_policy": "impute_mean"}, DEPT)
    rep, table = validate_dataset(df, f, "id")
    assert rep["ok"] and table.values["skill"][1] == 2.0 and any(w["code"] == "imputed" for w in rep["warnings"])
    assert table.ids == ["a", "b", "c"]  # nobody dropped


def test_missing_column_and_unknown_category_and_range():
    df = load("id,skill,dept\na,5,x\nb,1,zzz\n")
    f = feats({**SK, "min": 0, "max": 3}, {**DEPT, "categories": ["x", "y"]}, {"name": "ghost", "type": "binary"})
    rep, _ = validate_dataset(df, f, "id")
    codes = {e["code"] for e in rep["errors"]}
    assert {"out_of_range", "unknown_category", "missing_column"} <= codes


def test_integer_and_binary_parsing():
    df = load("id,yrs,py\na,2.5,maybe\nb,3,yes\n")
    rep, _ = validate_dataset(df, feats({"name": "yrs", "type": "numeric_integer"}, {"name": "py", "type": "binary"}), "id")
    assert sum(e["code"] == "invalid_value" for e in rep["errors"]) == 2


def test_schema_validation():
    with pytest.raises(SchemaError):
        parse_features([])
    with pytest.raises(SchemaError):
        parse_features([{"name": "a", "type": "weird"}])
    with pytest.raises(SchemaError):  # categorical value role without explicit scores
        parse_features([{"name": "a", "type": "categorical", "role": "value"}])
    with pytest.raises(SchemaError):
        parse_features([{"name": "a", "type": "binary"}, {"name": "a", "type": "binary"}])
    with pytest.raises(SchemaError):
        parse_features([{"name": "a", "type": "binary", "importance": -1}])
