import pytest
from optimization.models import Graph
from optimization.mwcp_solver import solve_clique
from optimization.brute_force_reference import brute_force_mwcp
from .helpers import rand_graph


@pytest.mark.parametrize("coloring", [True, False])
def test_empty_graph(coloring):
    g = Graph.from_edges(0, [])
    r = solve_clique(g, min_size=0, use_coloring=coloring)
    assert r.members == [] and r.score == 0 and r.optimal


@pytest.mark.parametrize("coloring", [True, False])
def test_single_vertex(coloring):
    g = Graph.from_edges(1, [], [2.5])
    r = solve_clique(g, use_coloring=coloring)
    assert r.members == [0] and r.score == 2.5 and r.optimal


@pytest.mark.parametrize("coloring", [True, False])
def test_complete_graph(coloring):
    n = 6
    g = Graph.from_edges(n, [(i, j) for i in range(n) for j in range(i + 1, n)], [1, 2, 3, 4, 5, 6])
    r = solve_clique(g, use_coloring=coloring)
    assert sorted(r.members) == list(range(n)) and r.score == 21


@pytest.mark.parametrize("coloring", [True, False])
def test_no_edges_picks_heaviest_vertex(coloring):
    g = Graph.from_edges(4, [], [1, 7, 3, 2])
    r = solve_clique(g, use_coloring=coloring)
    assert r.members == [1] and r.score == 7


def test_min_size_infeasible_reports_infeasible_not_optimal():
    g = Graph.from_edges(4, [], [1, 7, 3, 2])
    r = solve_clique(g, min_size=2)
    assert r.status == "infeasible" and not r.found and not r.optimal


@pytest.mark.parametrize("coloring", [True, False])
def test_unique_maximum(coloring):
    # triangle {0,1,2} weight 6 vs edge {3,4} weight 9 -> unique optimum {3,4}
    g = Graph.from_edges(5, [(0, 1), (1, 2), (0, 2), (3, 4)], [2, 2, 2, 4.5, 4.5])
    assert sorted(solve_clique(g, use_coloring=coloring).members) == [3, 4]


@pytest.mark.parametrize("coloring", [True, False])
def test_equal_optima_have_equal_score(coloring):
    g = Graph.from_edges(4, [(0, 1), (2, 3)], [1, 1, 1, 1])
    r = solve_clique(g, use_coloring=coloring)
    assert r.score == 2 and sorted(r.members) in ([0, 1], [2, 3])


def test_zero_weights():
    g = Graph.from_edges(3, [(0, 1)], [0, 0, 0])
    r = solve_clique(g, use_coloring=True)
    assert r.score == 0 and r.found


def test_invalid_inputs():
    g = Graph.from_edges(3, [(0, 1)], [1, 1, 1])
    with pytest.raises(ValueError):
        solve_clique(g, min_size=3, max_size=2)
    with pytest.raises(ValueError):
        solve_clique(g, forced=9)
    with pytest.raises(ValueError):
        Graph.from_edges(3, [(0, 0)])
    bad = Graph(ids=["a", "b"], vw=[1, -1], ew=[[0, 0], [0, 0]], adj=[0, 0])
    with pytest.raises(ValueError):
        solve_clique(bad)
    asym = Graph(ids=["a", "b"], vw=[1, 1], ew=[[0, 0], [0, 0]], adj=[2, 0])
    with pytest.raises(ValueError):
        solve_clique(asym)


@pytest.mark.parametrize("seed", range(60))
@pytest.mark.parametrize("coloring", [True, False])
def test_matches_brute_force(seed, coloring):
    n = 3 + seed % 8
    g = rand_graph(seed, n, p=0.3 + (seed % 5) * 0.15, edge_weights=seed % 2 == 0)
    kmin, kmax = 1 + seed % 2, 2 + seed % 4
    exp, _ = brute_force_mwcp(g, kmin, kmax)
    r = solve_clique(g, kmin, kmax, use_coloring=coloring)
    if exp is None:
        assert not r.found and r.status == "infeasible"
    else:
        assert r.optimal and abs(r.score - exp) < 1e-9
        assert g.is_clique(r.members) and kmin <= len(r.members) <= kmax


def test_pruning_happens_and_modes_agree():
    g = rand_graph(7, 16, p=0.7)
    on, off = solve_clique(g, 1, 6, True), solve_clique(g, 1, 6, False)
    assert abs(on.score - off.score) < 1e-9
    assert on.stats.pruned_by_bound > 0 and off.stats.pruned_by_bound > 0


def test_node_limit_is_not_reported_optimal():
    g = rand_graph(3, 18, p=0.8)
    r = solve_clique(g, 1, 8, node_limit=3)
    assert r.status == "node_limit" and not r.optimal
