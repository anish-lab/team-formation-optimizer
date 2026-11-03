import random
import pytest
from itertools import combinations
from optimization.bbmcw import bits, solve_bbmcw, degeneracy_order
from optimization.models import Graph
from .brute_force import brute_force_mwcp


def rg(seed, n, p, ints=True):
    rng = random.Random(seed)
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < p]
    w = [rng.randint(1, 10) if ints else round(rng.random() * 5, 3) for _ in range(n)]
    return Graph.from_edges(n, edges, w)


def test_trivial_cases():
    assert solve_bbmcw([], []).weight == 0
    r = solve_bbmcw([4.0], [0])
    assert r.members == [0] and r.weight == 4 and r.optimal
    r = solve_bbmcw([1, 7, 3], [0, 0, 0])                      # no edges
    assert r.members == [1] and r.weight == 7
    r = solve_bbmcw([1, 2, 3], [6, 5, 3])                      # triangle
    assert r.members == [0, 1, 2] and r.weight == 6
    assert solve_bbmcw([0, 0], [2, 1]).weight == 0             # zero weights


def test_invalid_input():
    with pytest.raises(ValueError):
        solve_bbmcw([1, -1], [0, 0])
    with pytest.raises(ValueError):
        solve_bbmcw([1, 1], [2, 0])                            # asymmetric


def test_degeneracy_order_is_permutation():
    g = rg(1, 9, 0.5)
    assert sorted(degeneracy_order(g.vw, g.adj)) == list(range(9))


@pytest.mark.parametrize("seed", range(120))
def test_matches_brute_force(seed):
    n = 2 + seed % 12
    g = rg(seed, n, 0.2 + (seed % 7) * 0.12, ints=seed % 3 != 0)
    exp, _ = brute_force_mwcp(g, 1, n)
    r = solve_bbmcw(g.vw, g.adj)
    assert r.optimal and abs(r.weight - exp) < 1e-9
    assert g.is_clique(r.members) and abs(sum(g.vw[i] for i in r.members) - r.weight) < 1e-9


@pytest.mark.parametrize("seed", range(10))
def test_matches_full_enumeration_on_larger_graphs(seed):
    g = rg(100 + seed, 26, 0.6 + 0.03 * seed)
    a = solve_bbmcw(g.vw, g.adj)

    def reference(P, total):                                  # plain enumeration of every clique, sharing no code with the solver
        best = total
        for v in bits(P):
            best = max(best, reference(P & g.adj[v] & ~((1 << (v + 1)) - 1), total + g.vw[v]))
        return best

    assert a.optimal and abs(a.weight - reference((1 << g.n) - 1, 0.0)) < 1e-9
    for off in ({"use_mcover": False}, {"use_cover": False, "use_mcover": False}, {"use_amts": False}, {"max_set_size": None}):
        assert abs(solve_bbmcw(g.vw, g.adj, **off).weight - a.weight) < 1e-9


@pytest.mark.parametrize("seed", range(40))
def test_pruned_set_property_holds(seed):
    """Defining property of the Pruned Set P = V\\B: omega(G[P]) <= lb - w(C) for every branching-set call."""
    g = rg(500 + seed, 7 + seed % 6, 0.3 + (seed % 6) * 0.12)
    checks = []

    def hook(V, budget, B):
        P = [v for v in bits(V) if v not in B]
        checks.append((P, budget))

    solve_bbmcw(g.vw, g.adj, hook=hook, preordered=True)
    w, A = g.vw, g.adj
    for P, budget in checks:
        best = 0.0
        for k in range(1, len(P) + 1):
            for S in combinations(P, k):
                if all((A[a] >> b) & 1 for a, b in combinations(S, 2)):
                    best = max(best, sum(w[x] for x in S))
        assert best <= budget + 1e-6


def test_limits_are_not_reported_optimal():
    g = rg(3, 40, 0.8)
    r = solve_bbmcw(g.vw, g.adj, node_limit=1)
    assert r.status in ("node_limit", "optimal")
    if r.status == "node_limit":
        assert not r.optimal
