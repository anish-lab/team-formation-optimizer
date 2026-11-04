import pytest
from data.csv_loader import read_csv_bytes
from data.feature_schema import parse_features
from data.validation import validate_dataset
from graph.builder import build_graph, ObjectiveConfig

CSV = "id,skill,dept,py\na,10,x,1\nb,0,x,0\nc,10,y,1\nd,5,y,0\n"


def table(specs):
    df = read_csv_bytes("t.csv", CSV.encode(), 10**6)
    rep, t = validate_dataset(df, parse_features(specs), "id")
    assert rep["ok"], rep["errors"]
    return t


SPECS = [{"name": "skill", "type": "numeric_continuous", "role": "both", "importance": 1},
         {"name": "dept", "type": "categorical", "role": "compat", "importance": 1},
         {"name": "py", "type": "binary", "role": "value", "importance": 1}]


def test_values_compat_and_scaling():
    b = build_graph(table(SPECS), ObjectiveConfig(alpha=1, beta=1, edge_mode="soft", preferred_size=2))
    g = b.graph
    assert g.raw_value[0] == pytest.approx(1.0) and g.raw_value[1] == 0.0       # skill 1.0 & py 1 ; skill 0 & py 0
    assert g.raw_compat[0][1] == pytest.approx((0.0 + 1.0) / 2)                 # skill sim 0, dept sim 1
    assert g.raw_compat[0][2] == pytest.approx((1.0 + 0.0) / 2)
    assert g.vw[0] == pytest.approx(1.0 / 2) and g.ew[0][1] == pytest.approx(0.5 / 1)   # k_ref=2: C(2,2)=1


def test_hard_threshold_removes_edges_and_is_deterministic():
    o = ObjectiveConfig(edge_mode="hard", threshold=0.75, preferred_size=2)
    g1, g2 = build_graph(table(SPECS), o).graph, build_graph(table(SPECS), o).graph
    assert g1.adj == g2.adj and g1.ew == g2.ew
    assert not g1.is_edge(0, 1) and g1.ew[0][1] == 0.0


def test_complementarity():
    specs = [{"name": "skill", "type": "numeric_continuous", "role": "compat", "compat_method": "complementarity"}]
    b = build_graph(table(specs), ObjectiveConfig(edge_mode="soft"))
    assert b.graph.raw_compat[0][1] == pytest.approx(1.0) and b.graph.raw_compat[0][2] == pytest.approx(0.0)


def test_matrix_must_be_complete_and_ids_not_features_by_default():
    specs = [{"name": "dept", "type": "categorical", "role": "compat", "compat_method": "matrix", "compat_matrix": {"x|x": 1, "y|y": 1}}]
    with pytest.raises(ValueError):
        build_graph(table(specs), ObjectiveConfig())
    t = table(SPECS)
    assert "id" not in t.values   # candidate IDs are never optimisation features unless the user adds them
