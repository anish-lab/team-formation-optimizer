import pytest
from optimization.constraints import resolve_constraints, check_feasibility, validate_assignment, ConstraintError
from optimization.models import Graph


def feas(n, **cfg):
    tc = resolve_constraints(n, cfg)
    return tc, check_feasibility(n, tc)


def test_policy_A_leave_unassigned_50_pref_4():
    tc, iss = feas(50, policy="leave_unassigned", preferred_size=4)
    assert (tc.teams_min, tc.teams_max, tc.min_size, tc.max_size) == (12, 12, 4, 4) and not iss


def test_policy_B_variable_sizes_12_teams_4_to_5():
    tc, iss = feas(50, policy="variable_sizes", preferred_size=4, num_teams=12, min_size=4, max_size=5, full_coverage=True)
    assert not iss and tc.full_coverage


def test_policy_C_smaller_final_team():
    tc, iss = feas(50, policy="smaller_final_team", preferred_size=4, min_size=2)
    assert not iss and tc.teams_max == 13 and tc.full_coverage and tc.max_short_teams == 1
    # 13 teams of size 4 with <=1 short covers exactly 50 = 12*4 + 2
    _, bad = feas(49 + 4, policy="smaller_final_team", preferred_size=4, min_size=3)  # 53 = 13*4+1 needs short size 1 < min 3
    assert bad


def test_policy_D_strict_equal_reports_leftover_count():
    tc, iss = feas(50, policy="strict_equal", preferred_size=4)
    assert tc.teams_max == 12 and tc.equal_sizes and not iss


def test_policy_E_full_coverage_infeasible_has_suggestions():
    tc, iss = feas(50, policy="full_coverage", preferred_size=4, min_size=4, max_size=4, num_teams=12)
    assert iss and iss[0]["code"] == "infeasible_counts" and iss[0]["suggestions"]


def test_too_few_candidates_and_bad_settings():
    _, iss = feas(3, policy="strict_equal", preferred_size=4)
    assert iss
    with pytest.raises(ConstraintError):
        resolve_constraints(10, {"policy": "nope"})
    with pytest.raises(ConstraintError):
        resolve_constraints(10, {"min_size": 5, "max_size": 3})
    with pytest.raises(ConstraintError):
        resolve_constraints(10, {"preferred_size": 0})


def test_validate_assignment_detects_violations():
    g = Graph.from_edges(4, [(0, 1), (1, 2), (2, 3)], [1] * 4)
    tc = resolve_constraints(4, {"policy": "leave_unassigned", "preferred_size": 2})
    assert validate_assignment(g, tc, [[0, 1], [2, 3]]) == []
    assert validate_assignment(g, tc, [[0, 1], [1, 2]])          # overlap
    assert validate_assignment(g, tc, [[0, 2], [1, 3]])          # not cliques
    assert validate_assignment(g, tc, [[0, 1]])                  # wrong team count
