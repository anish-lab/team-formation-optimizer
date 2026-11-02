import pytest
from optimization.models import Graph
from optimization.constraints import TeamConstraints, resolve_constraints, validate_assignment, assignment_key
from optimization.multi_team_solver import solve_multi_team
from optimization.greedy_baseline import greedy_teams
from optimization.brute_force_reference import brute_force_multi
from .helpers import rand_graph


def tc(**kw):
    base = dict(min_size=2, max_size=2, teams_min=1, teams_max=2, full_coverage=False, equal_sizes=False,
                preferred_size=2, max_short_teams=None, priority="coverage_first")
    base.update(kw)
    return TeamConstraints(**base)


CONFIGS = [
    dict(min_size=2, max_size=2, teams_min=2, teams_max=2),                                   # exact count, strict size
    dict(min_size=2, max_size=3, teams_min=1, teams_max=3),                                   # variable sizes
    dict(min_size=2, max_size=3, teams_min=1, teams_max=3, full_coverage=True),               # use everyone
    dict(min_size=1, max_size=3, teams_min=1, teams_max=4, priority="quality_first"),
    dict(min_size=2, max_size=3, teams_min=2, teams_max=3, equal_sizes=True),
    dict(min_size=1, max_size=3, teams_min=2, teams_max=3, max_short_teams=1, preferred_size=3, full_coverage=True),
]


@pytest.mark.parametrize("seed", range(36))
@pytest.mark.parametrize("coloring", [True, False])
def test_matches_brute_force(seed, coloring):
    n = 5 + seed % 4
    g = rand_graph(seed, n, p=0.45 + (seed % 4) * 0.15, edge_weights=seed % 3 != 0)
    c = tc(**CONFIGS[seed % len(CONFIGS)])
    exp_key, _ = brute_force_multi(g, c)
    r = solve_multi_team(g, c, use_coloring=coloring)
    if exp_key is None:
        assert r.status == "infeasible" and not r.teams
    else:
        assert r.status == "optimal" and r.optimality_proven
        key = assignment_key(g, c, [t.members for t in r.teams])
        assert key[0] == exp_key[0] and abs(key[1] - exp_key[1]) < 1e-9
        assert validate_assignment(g, c, [t.members for t in r.teams]) == []


def test_greedy_is_suboptimal_where_exact_succeeds():
    # path 0-1-2-3, middle vertices heavy: greedy takes {1,2} and cannot form a second team
    g = Graph.from_edges(4, [(0, 1), (1, 2), (2, 3)], [1, 10, 10, 1])
    c = tc(teams_min=2, teams_max=2)
    exact = solve_multi_team(g, c)
    assert exact.status == "optimal" and len(exact.teams) == 2 and exact.coverage == 4
    gr, violations = greedy_teams(g, c)
    assert gr.status == "heuristic" and not gr.optimality_proven and violations
    # greedy also has a lower total when the count is not mandatory
    c2 = tc(teams_min=1, teams_max=2, priority="quality_first")
    assert solve_multi_team(g, c2).total_score >= greedy_teams(g, c2)[0].total_score


def test_multiple_optima_and_no_overlap():
    n = 6
    g = Graph.from_edges(n, [(i, j) for i in range(n) for j in range(i + 1, n)], [1] * n)
    r = solve_multi_team(g, tc(min_size=3, max_size=3, teams_min=2, teams_max=2, preferred_size=3))
    assert r.optimality_proven and r.coverage == 6
    assert len({m for t in r.teams for m in t.members}) == 6


def test_infeasible_precheck_and_infeasible_graph():
    g = Graph.from_edges(5, [], [1] * 5)
    r = solve_multi_team(g, tc(min_size=3, max_size=3, teams_min=2, teams_max=2))
    assert r.status == "infeasible" and r.issues
    r2 = solve_multi_team(g, tc(min_size=2, max_size=2, teams_min=1, teams_max=2))
    assert r2.status == "infeasible" and r2.termination_reason == "search_completed"


def test_time_limit_gives_non_optimal_status():
    g = rand_graph(5, 22, p=0.9)
    r = solve_multi_team(g, tc(min_size=3, max_size=4, teams_min=1, teams_max=5), node_limit=5, max_cliques=2_000_000)
    assert not r.optimality_proven and r.status in ("feasible_not_proven", "no_solution_found")


def test_clique_cap_is_reported():
    g = rand_graph(5, 20, p=1.0)
    r = solve_multi_team(g, tc(min_size=4, max_size=4, teams_min=1, teams_max=5), max_cliques=100)
    assert r.status == "too_large" and not r.optimality_proven


def test_coloring_modes_same_optimum():
    g = rand_graph(11, 12, p=0.7)
    c = tc(min_size=3, max_size=3, teams_min=2, teams_max=3, preferred_size=3)
    a, b = solve_multi_team(g, c, True), solve_multi_team(g, c, False)
    assert abs(a.total_score - b.total_score) < 1e-9 and a.coverage == b.coverage
