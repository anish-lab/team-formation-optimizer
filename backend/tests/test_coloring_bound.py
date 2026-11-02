import random
from itertools import combinations
from optimization.coloring_bound import greedy_coloring, vertex_bounds, plain_upper_bound, coloring_upper_bound, bits
from .helpers import rand_graph


def test_coloring_is_proper_and_partitions():
    for seed in range(30):
        g = rand_graph(seed, 4 + seed % 10, p=0.5)
        cls = greedy_coloring(g.adj, list(range(g.n)))
        assert sorted(v for c in cls for v in c) == list(range(g.n))
        for c in cls:
            assert all(not g.is_edge(a, b) for a, b in combinations(c, 2))


def test_bound_never_below_true_gain():
    rng = random.Random(1)
    for seed in range(80):
        g = rand_graph(seed, 5 + seed % 6, p=0.7)
        # random clique R
        R = []
        for v in rng.sample(range(g.n), g.n):
            if all(g.is_edge(v, u) for u in R) and rng.random() < 0.5:
                R.append(v)
        P = (1 << g.n) - 1
        for u in R:
            P &= g.adj[u]
        verts = list(bits(P))
        for cap in (1, 2, 3, 4):
            m = cap
            b = vertex_bounds(g, R, verts, m)
            ub_c, _ = coloring_upper_bound(g.adj, b, verts, m)
            ub_p = plain_upper_bound(b, m)
            base = g.score(R)
            true_gain = 0.0
            for k in range(0, m + 1):
                for S in combinations(verts, k):
                    if g.is_clique(S):
                        true_gain = max(true_gain, g.score(list(R) + list(S)) - base)
            assert ub_c >= true_gain - 1e-9 and ub_p >= true_gain - 1e-9
            assert ub_c <= ub_p + 1e-9
