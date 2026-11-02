"""Greedy baseline: repeatedly take the best remaining clique (found with the exact single-clique solver).

HEURISTIC - no optimality guarantee.  It respects the size / equal-size / short-team rules while picking each
team, but it may stop with too few teams or leave candidates unassigned when full coverage / a mandatory team
count was requested; such outputs are flagged via `violations` rather than silently accepted.
"""
from __future__ import annotations
import time
from .models import Graph
from .constraints import TeamConstraints, validate_assignment
from .mwcp_solver import solve_clique
from .multi_team_solver import MultiResult, Team


def greedy_teams(graph: Graph, tc: TeamConstraints, use_coloring: bool = True) -> tuple[MultiResult, list[str]]:
    t0 = time.perf_counter()
    avail = (1 << graph.n) - 1
    teams: list[Team] = []
    nodes = 0
    while len(teams) < tc.teams_max:
        lo, hi = tc.min_size, tc.max_size
        if tc.equal_sizes and teams:
            lo = hi = len(teams[0].members)
        if tc.max_short_teams is not None and sum(len(t.members) < tc.preferred_size for t in teams) >= tc.max_short_teams:
            lo = max(lo, tc.preferred_size)
        res = solve_clique(graph, lo, hi, use_coloring, allowed=avail, validate=False)
        nodes += res.stats.nodes
        if not res.found:
            break
        v, c = graph.score_parts(res.members)
        teams.append(Team(sorted(res.members), v + c, v, c))
        for m in res.members:
            avail &= ~(1 << m)
    violations = validate_assignment(graph, tc, [t.members for t in teams])
    assigned = {m for t in teams for m in t.members}
    out = MultiResult("heuristic", False, "greedy_completed", teams=teams,
                      unassigned=[v for v in range(graph.n) if v not in assigned],
                      total_score=sum(t.score for t in teams), coverage=len(assigned),
                      stats={"nodes": nodes, "total_runtime_s": time.perf_counter() - t0})
    return out, violations
