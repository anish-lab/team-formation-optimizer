"""The worked examples printed in San Segundo, Furini & Artieda (2019), page numbers from the 36-page preprint."""
from optimization.amts import amts
from optimization.bbmcw import bits, colour_sort_order, degeneracy_order, gen_branch_set, relabel, solve_bbmcw
from optimization.models import Graph


def branching_set(weights, edges, budget):
    """GenBranchSet's result for the whole graph with the given budget.

    An isolated dummy vertex of weight `budget` is the incumbent, and is removed from the candidates at the root.
    """
    n = len(weights)
    g = Graph.from_edges(n + 1, edges, list(weights) + [budget])
    dummy = 1 << n
    seen = []
    solve_bbmcw(g.vw, g.adj, node_limit=1, initial=[n], preordered=True, restrict=lambda C, V, b: V & ~dummy,
                hook=lambda V, b, B: seen.append((sorted(bits(V)), b, list(B))))
    return seen[0]


# Figure 1 (p. 2): vertices v1..v10 stored as 0..9
FIG1_W = [1, 2, 3, 4, 5, 1, 2, 3, 4, 5]
FIG1_E = [(7, 6), (7, 8), (6, 10), (8, 9), (10, 9), (7, 1), (7, 3), (6, 2), (6, 1), (8, 2), (8, 3), (1, 2), (2, 3), (1, 3), (1, 5),
          (1, 4), (1, 10), (2, 5), (2, 4), (3, 5), (3, 4), (3, 9), (5, 4), (5, 10), (5, 9), (4, 10), (4, 9)]


def test_figure_1_maximum_weighted_clique():
    g = Graph.from_edges(10, [(a - 1, b - 1) for a, b in FIG1_E], FIG1_W)
    r = solve_bbmcw(g.vw, g.adj)
    assert r.optimal and r.weight == 18                       # omega(G, w) = 18
    assert [m + 1 for m in r.members] == [4, 5, 9, 10]        # C = {v4, v5, v9, v10}


def test_rule_r3_example_needs_the_bound_of_6():
    # Section 2.2 (p. 10): I = {v8, v6} and v10.  R3 gives a bound of 6, so v10 is moved with budget 6 but not with 5.
    weights = [3, 1, 5]                                       # v8, v6, v10
    edges = [(1, 2)]                                          # only v6-v10 is an edge among these three
    assert branching_set(weights, edges, 6.0)[2] == []
    assert branching_set(weights, edges, 5.0)[2] == [2]


# Figure 2 (p. 19): vertices v0..v6, weights 1..7
FIG2_W = [1, 2, 3, 4, 5, 6, 7]
FIG2_CHILD = [(2, 5), (0, 2), (1, 5), (1, 6), (0, 1), (0, 4), (4, 5), (0, 6)]
FIG2_E = FIG2_CHILD + [(3, v) for v in (0, 1, 2, 4, 5, 6)]


def test_demonstration_graph_has_the_stated_size():
    assert len(FIG2_E) == 14                                  # n = 7, m = 14 (p. 18)
    assert sum(FIG2_W[v] for v in (0, 1, 3, 6)) == 14         # the initial clique has weight 14 (p. 18)


def test_demonstration_branching_set_after_cover_and_mcover():
    # Section 3 (pp. 18-21): subproblem N(v3), gap 14 - w(v3) = 10.  COLOR gives {v5, v0} and {v2, v1} with bound 9, leaving
    # B = {v4, v6}.  COVER moves nothing, MCOVER moves v6 (5 + 1 + gap 1 = 7), and the final B is {v4}.
    # Relabel v0 v1 v2 v4 v5 v6 as 0..5, which keeps the paper's order.
    label = {0: 0, 1: 1, 2: 2, 4: 3, 5: 4, 6: 5}
    weights = [1, 2, 3, 5, 6, 7]
    edges = [(label[a], label[b]) for a, b in FIG2_CHILD]
    V, budget, B = branching_set(weights, edges, 10.0)
    assert V == [0, 1, 2, 3, 4, 5] and budget == 10.0
    assert B == [label[4]]


def test_demonstration_mcover_is_what_moves_v6():
    # One unit less budget (gap 0 after COLOR) leaves MCOVER unable to cover w(v6) = 7 with its 6 units of capacity.
    label = {0: 0, 1: 1, 2: 2, 4: 3, 5: 4, 6: 5}
    edges = [(label[a], label[b]) for a, b in FIG2_CHILD]
    assert label[6] in branching_set([1, 2, 3, 5, 6, 7], edges, 9.0)[2]


def test_demonstration_graph_optimum_from_the_papers_incumbent():
    g = Graph.from_edges(7, FIG2_E, FIG2_W)
    r = solve_bbmcw(g.vw, g.adj, initial=[0, 1, 3, 6])
    assert r.optimal and r.weight == 15 and r.members == [3, 4, 5]        # beats the initial clique of weight 14


def test_figure_1_amts_finds_the_optimum_alone():
    g = Graph.from_edges(10, [(a - 1, b - 1) for a, b in FIG1_E], FIG1_W)
    members, weight = amts(g.vw, g.adj, range(1, 7))
    assert weight == 18 and sorted(m + 1 for m in members) == [4, 5, 9, 10]


def test_colour_sort_groups_vertices_by_colour():
    g = Graph.from_edges(7, FIG2_E, FIG2_W)
    order = colour_sort_order(g.adj, degeneracy_order(g.vw, g.adj))
    assert sorted(order) == list(range(7))
    # consecutive vertices of one greedy colour class are never adjacent: count the classes along the order
    classes, current = 0, 0
    for v in order:
        if classes == 0 or g.adj[v] & current:
            classes, current = classes + 1, 0
        current |= 1 << v
    assert classes <= 4


def test_three_vertex_limit_keeps_the_pruned_set_valid():
    # Section 2.6 (p. 17).  An independent set of 5, then v joins only by treating the dropped vertices as its neighbours.
    weights = [9, 8, 7, 6, 5, 4]
    edges = [(4, 5)]                                          # v (index 5) is adjacent only to a vertex the limit drops
    full = gen_branch_set((1 << 6) - 1, 9.0, weights, Graph.from_edges(6, edges, weights).adj, max_set_size=None)
    capped = gen_branch_set((1 << 6) - 1, 9.0, weights, Graph.from_edges(6, edges, weights).adj, max_set_size=3)
    assert set(full) <= set(capped) or set(capped) <= set(full)
    r = solve_bbmcw(weights, Graph.from_edges(6, edges, weights).adj)
    assert r.optimal and r.weight == 9
