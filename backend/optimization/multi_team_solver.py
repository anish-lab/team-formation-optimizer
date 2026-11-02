"""Exact multi-team optimiser (set packing with cardinality / size rules) on top of the MWCP machinery.

The app now forms teams with team_conflict_solver.py (BBMCW).  This solver is kept as an independent comparison.

Formulation
-----------
Choose a set of pairwise vertex-disjoint cliques T_1..T_k (teams), each of size in [kmin,kmax], with
k in [teams_min, teams_max], maximising lexicographically
    coverage_first : (number of assigned candidates, sum of team scores)
    quality_first  : (sum of team scores)
subject to the hard constraints in constraints.py.  (Ties: first solution found in the fixed search order.)

Algorithm
---------
1. Enumerate all feasible team cliques once, grouped by their smallest vertex (memory-capped).
2. best_by_min[v] = value of the best single team whose smallest vertex is v, computed with the exact
   MWCP Branch-and-Bound (solve_clique, forced=v, colouring on/off).
3. Outer Branch-and-Bound over vertices 0..n-1 in index order.  At the lowest undecided vertex v either
   (a) open a team with smallest vertex v (any enumerated clique avoiding used vertices), or
   (b) leave v unassigned (only if full coverage is not required).
   Every partial assignment is generated exactly once, so the search is exhaustive.
4. Bound at a node: coverage <= covered + min(free vertices >= v, r * size_cap) and
   quality <= quality_so_far + sum of the r largest best_by_min[u] over free u >= v  (r = remaining teams;
   remaining teams have distinct smallest vertices).  Both are valid, so pruning is safe.
This is NOT "repeat the best clique and stop": teams are chosen jointly, so the optimum is global for the
selected objective and constraints whenever status == "optimal".
"""
from __future__ import annotations
import sys
import time
from dataclasses import dataclass, field
from .models import Graph
from .constraints import TeamConstraints, check_feasibility, validate_assignment
from .clique_generation import enumerate_cliques, CliqueLimitExceeded
from .mwcp_solver import solve_clique
from .statistics import SearchStats

EPS = 1e-12


@dataclass
class Team:
    members: list[int]
    score: float
    value_score: float
    compat_score: float


@dataclass
class MultiResult:
    status: str  # optimal | infeasible | feasible_not_proven | no_solution_found | too_large | heuristic
    optimality_proven: bool
    termination_reason: str
    teams: list[Team] = field(default_factory=list)
    unassigned: list[int] = field(default_factory=list)
    total_score: float = 0.0
    coverage: int = 0
    stats: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    root_bound: float | None = None
    covered_by_some_team: list[bool] = field(default_factory=list)


class _Stop(Exception):
    def __init__(self, reason):
        self.reason = reason


def _better(a, b):
    if a[0] != b[0]:
        return a[0] > b[0]
    return a[1] > b[1] + EPS


def solve_multi_team(graph: Graph, tc: TeamConstraints, use_coloring: bool = True, time_limit: float | None = None,
                     node_limit: int | None = None, max_cliques: int = 250_000, should_stop=None,
                     progress: dict | None = None) -> MultiResult:
    graph.validate()
    n = graph.n
    t0 = time.perf_counter()
    outer, inner = SearchStats(), SearchStats()
    progress = progress if progress is not None else {}

    def stats_dict():
        o = outer.to_dict()
        return {**o, "mwcp_phase": inner.to_dict(), "use_coloring": use_coloring, "root_quality_bound": progress.get("root_bound"),
                "total_runtime_s": time.perf_counter() - t0}

    def deadline_left():
        return None if time_limit is None else max(time_limit - (time.perf_counter() - t0), 0.0)

    issues = check_feasibility(n, tc)
    if issues:
        return MultiResult("infeasible", False, "feasibility_check", issues=issues, stats=stats_dict())

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 4 * n + 500))
    try:
        by_min = enumerate_cliques(graph, tc.min_size, tc.max_size, max_cliques, should_stop)
    except CliqueLimitExceeded as e:
        reason = "cancelled" if str(e) == "stopped" else "clique_limit_exceeded"
        return MultiResult("no_solution_found" if reason == "cancelled" else "too_large", False, reason,
                           issues=[{"code": reason, "message": f"Team enumeration aborted ({e}).",
                                    "suggestions": ["Raise the compatibility threshold to sparsify the graph",
                                                    "Reduce team size or candidate count",
                                                    "Allow the labelled heuristic fallback"]}],
                           stats=stats_dict())
    covered = [False] * n
    for lst in by_min:
        for c in lst:
            for v in c.members:
                covered[v] = True
        lst.sort(key=lambda c: (-c.score, c.members))
    outer.complete_teams_examined = sum(len(x) for x in by_min)

    # --- step 2: exact single-team optimum per smallest vertex (MWCP B&B) ---
    bbm: list[float | None] = [None] * n
    for v in range(n):
        if not by_min[v]:
            continue
        res = solve_clique(graph, tc.min_size, tc.max_size, use_coloring, forced=v,
                           allowed=((1 << n) - 1) ^ ((1 << v) - 1), time_limit=deadline_left(),
                           should_stop=should_stop, validate=False)
        inner.merge(res.stats)
        if not res.optimal:
            return MultiResult("no_solution_found", False, res.status, stats=stats_dict(),
                               covered_by_some_team=covered)
        bbm[v] = res.score
    _vals = sorted((x for x in bbm if x is not None), reverse=True)
    root_bound = sum(_vals[: tc.teams_max])   # valid upper bound on the total team-quality term of ANY assignment
    progress["root_bound"] = root_bound

    full_mask = (1 << n) - 1
    best = {"key": None, "teams": None}
    tcap, tmin_t, tmax_t = tc.max_size, tc.min_size, tc.teams_max
    cov_first = tc.priority == "coverage_first"

    def mk(cov, q):
        return (cov if cov_first else 0, q)

    def sync():
        progress.update(nodes=outer.nodes, pruned_by_bound=outer.pruned_by_bound,
                        pruned_by_feasibility=outer.pruned_by_feasibility,
                        incumbent_updates=outer.incumbent_updates,
                        incumbent_score=None if best["key"] is None else best["key"][1],
                        incumbent_coverage=None if best["teams"] is None else sum(c.size for c in best["teams"]))

    def rec(v, used, chosen, cov, q, short, fixed):
        outer.nodes += 1
        if should_stop is not None and should_stop():
            raise _Stop("cancelled")
        if node_limit is not None and outer.nodes > node_limit:
            raise _Stop("node_limit")
        if time_limit is not None and time.perf_counter() - t0 > time_limit:
            raise _Stop("time_limit")
        while v < n and (used >> v) & 1:
            v += 1
        if v == n:
            if tc.teams_min <= len(chosen) <= tc.teams_max:
                k = mk(cov, q)
                if best["key"] is None or _better(k, best["key"]):
                    best["key"], best["teams"] = k, list(chosen)
                    outer.incumbent_updates += 1
            sync()
            return
        free = (full_mask & ~used) >> v << v
        avail = free.bit_count()
        r = tmax_t - len(chosen)
        smin, smax = (fixed, fixed) if fixed else (tmin_t, tcap)
        need = max(0, tc.teams_min - len(chosen))
        if need > r or avail < need * smin or (tc.full_coverage and avail > r * smax):
            outer.pruned_by_feasibility += 1
            return
        if best["key"] is not None:
            vals = sorted((bbm[u] for u in range(v, n) if not (used >> u) & 1 and bbm[u] is not None), reverse=True)
            ub = mk(cov + min(avail, r * smax), q + sum(vals[:r]))
            outer.bound_evaluations += 1
            if not _better(ub, best["key"]):
                outer.pruned_by_bound += 1
                return
        if (outer.nodes & 63) == 0:
            sync()
        if len(chosen) < tmax_t:
            for c in by_min[v]:
                if c.mask & used:
                    continue
                if fixed and c.size != fixed:
                    continue
                is_short = tc.max_short_teams is not None and c.size < tc.preferred_size
                if is_short and short >= tc.max_short_teams:
                    continue
                outer.branches += 1
                chosen.append(c)
                rec(v + 1, used | c.mask, chosen, cov + c.size, q + c.score, short + is_short,
                    fixed or (c.size if tc.equal_sizes else 0))
                chosen.pop()
        if not tc.full_coverage:
            outer.branches += 1
            rec(v + 1, used, chosen, cov, q, short, fixed)

    reason = "search_completed"
    try:
        rec(0, 0, [], 0, 0.0, 0, 0)
    except _Stop as s:
        reason = s.reason
    sync()
    outer.runtime_s = time.perf_counter() - t0
    teams = []
    if best["teams"] is not None:
        teams = [Team(list(c.members), c.score, c.value_score, c.compat_score) for c in best["teams"]]
        teams.sort(key=lambda t: t.members[0])
        assert not validate_assignment(graph, tc, [t.members for t in teams]), "solver produced invalid assignment"
    assigned = {v for t in teams for v in t.members}
    res = MultiResult(
        status=("optimal" if teams else "infeasible") if reason == "search_completed"
        else ("feasible_not_proven" if teams else "no_solution_found"),
        optimality_proven=reason == "search_completed" and bool(teams),
        termination_reason=reason, teams=teams, unassigned=[v for v in range(n) if v not in assigned],
        total_score=sum(t.score for t in teams), coverage=len(assigned), stats=stats_dict(),
        covered_by_some_team=covered)
    if res.status == "infeasible":
        res.issues = [{"code": "no_valid_assignment",
                       "message": "The search was exhaustive: no assignment satisfies all constraints on this compatibility graph.",
                       "suggestions": ["Lower the compatibility threshold", "Allow unassigned candidates",
                                       "Reduce the required team count or size", "Allow variable team sizes"]}]
    return res
