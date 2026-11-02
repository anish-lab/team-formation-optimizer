import pytest
from optimization.bbmcw import degeneracy_order
from optimization.brute_force_reference import brute_force_multi
from optimization.clique_generation import enumerate_cliques
from optimization.constraints import TeamConstraints, assignment_key, validate_assignment
from optimization.models import Graph
from optimization.multi_team_solver import solve_multi_team
from optimization.team_conflict_solver import solve_teams_bbmcw, team_graph_order
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
    dict(min_size=2, max_size=3, teams_min=1, teams_max=2),                                   # cap binds, coverage varies
    dict(min_size=2, max_size=4, teams_min=2, teams_max=3, priority="quality_first"),
]


@pytest.mark.parametrize("seed", range(96))
def test_matches_brute_force(seed):
    n = 5 + seed % 4
    g = rand_graph(seed, n, p=0.4 + (seed % 5) * 0.15, edge_weights=seed % 3 != 0)
    c = tc(**CONFIGS[seed % len(CONFIGS)])
    exp_key, _ = brute_force_multi(g, c)
    r = solve_teams_bbmcw(g, c)
    if exp_key is None:
        assert r.status == "infeasible" and not r.teams
    else:
        assert r.status == "optimal" and r.optimality_proven
        key = assignment_key(g, c, [t.members for t in r.teams])
        assert key[0] == exp_key[0] and abs(key[1] - exp_key[1]) < 1e-9
        assert validate_assignment(g, c, [t.members for t in r.teams]) == []


@pytest.mark.parametrize("seed", range(24))
def test_agrees_with_previous_solver_on_larger_graphs(seed):
    g = rand_graph(300 + seed, 12 + seed % 5, p=0.5 + (seed % 4) * 0.15)
    c = tc(**CONFIGS[seed % len(CONFIGS)])
    a, b = solve_teams_bbmcw(g, c), solve_multi_team(g, c)
    assert a.status == b.status
    if a.optimality_proven:
        assert abs(a.total_score - b.total_score) < 1e-9
        assert c.priority == "quality_first" or a.coverage == b.coverage


@pytest.mark.parametrize("seed", range(10))
def test_team_graph_order_equals_paper_degeneracy_order(seed):
    g = rand_graph(seed, 10, p=0.7)
    teams = [t for lst in enumerate_cliques(g, 2, 3) for t in lst]
    w = [t.score for t in teams]
    adj = [sum(1 << j for j, u in enumerate(teams) if not t.mask & u.mask) for t in teams]
    assert team_graph_order(teams, w, g.n) == degeneracy_order(w, adj)


def test_finds_the_joint_optimum_that_greedy_misses():
    # path 0-1-2-3, middle vertices heavy: picking the best team {1,2} first rules out a second team
    g = Graph.from_edges(4, [(0, 1), (1, 2), (2, 3)], [1, 10, 10, 1])
    r = solve_teams_bbmcw(g, tc(teams_min=2, teams_max=2))
    assert r.status == "optimal" and sorted(t.members for t in r.teams) == [[0, 1], [2, 3]]


def test_coverage_outweighs_any_score():
    # one heavy pair versus two light pairs covering more people
    g = Graph.from_edges(4, [(0, 1), (2, 3), (1, 2)], [1, 100, 100, 1])
    assert solve_teams_bbmcw(g, tc()).coverage == 4
    r = solve_teams_bbmcw(g, tc(priority="quality_first"))
    assert r.optimality_proven and abs(r.total_score - 202) < 1e-9


def test_infeasible_precheck_and_infeasible_graph():
    g = Graph.from_edges(5, [], [1] * 5)
    r = solve_teams_bbmcw(g, tc(min_size=3, max_size=3, teams_min=2, teams_max=2))
    assert r.status == "infeasible" and r.termination_reason == "feasibility_check"
    r2 = solve_teams_bbmcw(g, tc(min_size=2, max_size=2, teams_min=1, teams_max=2))
    assert r2.status == "infeasible" and r2.termination_reason == "search_completed" and r2.issues


def test_stopped_search_is_not_reported_optimal():
    g = rand_graph(5, 22, p=0.9)
    r = solve_teams_bbmcw(g, tc(min_size=3, max_size=4, teams_min=1, teams_max=5), node_limit=5, max_cliques=2_000_000)
    assert not r.optimality_proven and r.status in ("feasible_not_proven", "no_solution_found")


def test_enumeration_cap_is_reported():
    g = rand_graph(5, 20, p=1.0)
    r = solve_teams_bbmcw(g, tc(min_size=4, max_size=4, teams_min=1, teams_max=5), max_cliques=100)
    assert r.status == "too_large" and not r.optimality_proven


def test_restricted_team_graph_is_never_reported_as_proven():
    g = rand_graph(7, 14, p=1.0)
    c = tc(min_size=3, max_size=4, teams_min=3, teams_max=3, preferred_size=3)
    r = solve_teams_bbmcw(g, c, max_conflict_vertices=100, time_limit=5)
    assert r.status == "feasible_not_proven" and not r.optimality_proven and r.stats["restricted"]
    assert any(i["code"] == "team_graph_restricted" for i in r.issues)
    assert validate_assignment(g, c, [t.members for t in r.teams]) == []


def test_reports_algorithm_and_team_graph_size():
    g = Graph.from_edges(4, [(0, 1), (2, 3)], [1, 1, 1, 1])
    st = solve_teams_bbmcw(g, tc()).stats
    assert st["algorithm"] == "bbmcw_team_graph" and st["team_graph_vertices"] == 2
