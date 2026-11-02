"""Team formation solved as a classical Maximum Weighted Clique Problem with BBMCW (bbmcw.py).

Reduction
---------
Build a new graph H, the *team graph*, from the candidate graph G:
  * one vertex of H per feasible team, i.e. per clique of G with size in [min_size, max_size];
  * weight of that vertex = the team's score (vertex values + pairwise compatibilities, already combined);
  * an edge between two vertices of H iff the two teams share no candidate.
A clique of H is exactly a set of pairwise disjoint teams, and its weight is the sum of their scores, so the maximum
weight clique of H is the best assignment.  This moves the two things BBMCW cannot express into H's construction: size
limits decide which vertices exist, and pairwise weights are folded into vertex weights.  BBMCW itself then runs on a
purely vertex-weighted graph with its bound, Branching Set and Pruned Set unchanged.

Rules that H cannot encode (team count, full coverage, equal sizes, at most one short team) are enforced through
BBMCW's `accept` and `restrict` arguments; see that module's docstring for why this keeps the search exact.

Coverage priority: coverage_first is lexicographic, encoded as weight = size * M + score with M > any total score,
and M = 0 whenever coverage cannot vary.  This is exact because a single extra assigned candidate outweighs all scores.

Beyond the paper: the reduction, restrict/accept and the two packing bounds in `restrict` are this project's own work.
If there are more feasible teams than `max_conflict_vertices`, only each candidate's best teams of each size are kept
(plus the starting solution's teams): the search then runs on a subset, so the result is reported as
feasible_not_proven even if the search finishes.
"""
from __future__ import annotations
import heapq
import time
import numpy as np
from .bbmcw import solve_bbmcw
from .clique_generation import enumerate_cliques, CliqueLimitExceeded, TeamClique
from .coloring_bound import bits
from .constraints import TeamConstraints, check_feasibility, validate_assignment
from .models import Graph
from .multi_team_solver import MultiResult, Team
from .statistics import SearchStats

ALGORITHM = "bbmcw_team_graph"
GREEDY_STARTS = 50
GREEDY_STEP_BUDGET = 2_000_000


def team_graph_order(teams: list[TeamClique], weights: list[float], n: int) -> list[int]:
    """Same result as bbmcw.degeneracy_order on the team graph, without building it first.

    Degree in H = (remaining teams) - (remaining teams sharing a candidate, itself included), so the minimum-degree
    team is the one with the most conflicts.  Ties: smaller weight, then smaller index.
    """
    N = len(teams)
    member = np.zeros((N, n), dtype=bool)
    for i, t in enumerate(teams):
        member[i, list(t.members)] = True
    conflicts = np.fromiter((member[:, list(t.members)].any(axis=1).sum() for t in teams), dtype=np.int64, count=N)
    w = np.asarray(weights, dtype=float)
    alive = np.ones(N, dtype=bool)
    order = [0] * N
    for pos in range(N - 1, -1, -1):
        c = np.where(alive, conflicts, -1)
        tied = np.flatnonzero(c == c.max())
        pick = int(tied[np.argmin(w[tied])])
        order[pos] = pick
        alive[pick] = False
        conflicts -= member[:, list(teams[pick].members)].any(axis=1)
    return order


def _keep_best_per_candidate(teams: list[TeamClique], n: int, cap: int, always: list[TeamClique]) -> list[TeamClique]:
    """Keep each candidate's highest-scoring teams of each size, so no candidate or size disappears because of the cap."""
    groups: dict[tuple[int, int], list[int]] = {}
    for i, t in enumerate(teams):
        for v in t.members:
            groups.setdefault((v, t.size), []).append(i)
    sizes = len({t.size for t in teams})
    quota = max(1, cap // max(n * sizes, 1))
    keep: set[int] = set()
    for lst in groups.values():
        keep.update(heapq.nlargest(quota, lst, key=lambda i: (teams[i].score, -i)))
    masks = {t.mask for t in always}
    keep.update(i for i, t in enumerate(teams) if t.mask in masks)
    return [teams[i] for i in sorted(keep)]


def _sizes_valid(sizes: list[int], tc: TeamConstraints, n: int) -> bool:
    """The rules a clique of the team graph does not enforce by itself."""
    if not tc.teams_min <= len(sizes) <= tc.teams_max:
        return False
    if tc.full_coverage and sum(sizes) != n:
        return False
    if tc.equal_sizes and len(set(sizes)) > 1:
        return False
    return tc.max_short_teams is None or sum(s < tc.preferred_size for s in sizes) <= tc.max_short_teams


def _greedy_packing(teams: list[TeamClique], weights: list[float], tc: TeamConstraints, n: int) -> list[TeamClique] | None:
    """Starting incumbent: pack teams best-first from several starting teams and keep the best valid packing."""
    ranked = sorted(range(len(teams)), key=lambda i: (-weights[i], i))
    starts = max(1, min(GREEDY_STARTS, GREEDY_STEP_BUDGET // max(len(teams), 1)))
    best, best_w = None, -1.0
    for s in ranked[:starts]:
        chosen, used, shorts = [teams[s]], teams[s].mask, int(teams[s].size < tc.preferred_size)
        total = weights[s]
        for i in ranked:
            if len(chosen) >= tc.teams_max:
                break
            t = teams[i]
            if t.mask & used or (tc.equal_sizes and t.size != chosen[0].size):
                continue
            is_short = t.size < tc.preferred_size
            if tc.max_short_teams is not None and is_short and shorts >= tc.max_short_teams:
                continue
            chosen.append(t)
            used |= t.mask
            shorts += is_short
            total += weights[i]
        if total > best_w and _sizes_valid([t.size for t in chosen], tc, n):
            best, best_w = chosen, total
    return best


def solve_teams_bbmcw(graph: Graph, tc: TeamConstraints, time_limit: float | None = None, node_limit: int | None = None,
                      max_cliques: int = 250_000, should_stop=None, progress: dict | None = None,
                      max_conflict_vertices: int = 20_000) -> MultiResult:
    graph.validate()
    n = graph.n
    t0 = time.perf_counter()
    stats = SearchStats()
    progress = progress if progress is not None else {}
    info = {"team_graph_vertices": 0, "team_graph_density": None, "restricted": False}

    def stats_dict():
        return {**stats.to_dict(), "algorithm": ALGORITHM, **info, "total_runtime_s": time.perf_counter() - t0}

    issues = check_feasibility(n, tc)
    if issues:
        return MultiResult("infeasible", False, "feasibility_check", issues=issues, stats=stats_dict())
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
    every_team = [c for lst in by_min for c in lst]
    covered = [False] * n
    for c in every_team:
        for v in c.members:
            covered[v] = True
    stats.complete_teams_examined = len(every_team)

    # --- vertex weights of H ---
    coverage_fixed = (tc.priority == "quality_first" or tc.full_coverage
                      or (tc.min_size == tc.max_size and tc.teams_min == tc.teams_max))
    M = 0.0 if coverage_fixed else float(int(sum(heapq.nlargest(tc.teams_max, (c.score for c in every_team)))) + 1)
    start = _greedy_packing(every_team, [c.size * M + c.score for c in every_team], tc, n) if every_team else None
    teams = every_team
    if len(teams) > max_conflict_vertices:
        teams = _keep_best_per_candidate(teams, n, max_conflict_vertices, start or [])
        info["restricted"] = True
    raw = [c.size * M + c.score for c in teams]

    # --- degeneracy ordering, then adjacency of H as bitsets: all teams minus those sharing a candidate ---
    order = team_graph_order(teams, raw, n) if teams else []
    teams = [teams[i] for i in order]
    w = [raw[i] for i in order]
    N = len(teams)
    full = (1 << N) - 1
    with_candidate = [0] * n
    size_mask: dict[int, int] = {}
    for pos, c in enumerate(teams):
        for v in c.members:
            with_candidate[v] |= 1 << pos
        size_mask[c.size] = size_mask.get(c.size, 0) | (1 << pos)
    adj = []
    for c in teams:
        clash = 0
        for v in c.members:
            clash |= with_candidate[v]
        adj.append(full & ~clash)
    info["team_graph_vertices"] = N
    info["team_graph_density"] = sum(a.bit_count() for a in adj) / (N * (N - 1)) if N > 1 else 0.0
    short_mask = 0
    if tc.max_short_teams is not None:
        for s, m in size_mask.items():
            if s < tc.preferred_size:
                short_mask |= m

    def accept(C: list[int]) -> bool:
        return _sizes_valid([teams[p].size for p in C], tc, n)

    def restrict(C: list[int], V: int, budget: float) -> int:
        r = tc.teams_max - len(C)
        if r <= 0:
            return 0
        used = 0
        sizes = []
        for p in C:
            used |= teams[p].mask
            sizes.append(teams[p].size)
        if tc.equal_sizes and sizes and sizes[0] in size_mask:
            V &= size_mask[sizes[0]]
        if tc.max_short_teams is not None and sum(s < tc.preferred_size for s in sizes) >= tc.max_short_teams:
            V &= ~short_mask
        free = n - used.bit_count()
        need = max(0, tc.teams_min - len(C))
        if free < need * tc.min_size:
            return 0
        if tc.full_coverage:
            if free > r * tc.max_size:
                return 0
            for v in bits(((1 << n) - 1) & ~used):
                if not V & with_candidate[v]:
                    return 0
        if budget >= 0 and V:
            # r more teams are worth at most the r heaviest teams left, and also at most the best per-member share
            # of the r * max_size candidates they can hold (a team's weight split equally over its members).
            in_V = list(bits(V))
            if sum(heapq.nlargest(r, (w[p] for p in in_V))) <= budget:
                return 0
            share = [0.0] * n
            for p in in_V:
                s = w[p] / teams[p].size
                for v in teams[p].members:
                    if s > share[v]:
                        share[v] = s
            if sum(heapq.nlargest(r * tc.max_size, share)) <= budget:
                return 0
        return V

    def sync():
        progress.update(nodes=stats.nodes, pruned_by_bound=stats.pruned_by_bound,
                        pruned_by_feasibility=stats.pruned_by_feasibility, incumbent_updates=stats.incumbent_updates)

    def report_incumbent(C, _weight):
        progress.update(incumbent_score=sum(teams[p].score for p in C),
                        incumbent_coverage=sum(teams[p].size for p in C))

    position = {c.mask: p for p, c in enumerate(teams)}
    initial = [position[t.mask] for t in start] if start else None
    if initial is not None:
        report_incumbent(initial, None)
    left = None if time_limit is None else max(time_limit - (time.perf_counter() - t0), 0.0)
    res = solve_bbmcw(w, adj, left, node_limit, should_stop, hook=lambda *_: sync(), accept=accept, restrict=restrict,
                      initial=initial, preordered=True, validate=False, on_incumbent=report_incumbent, stats=stats)
    sync()
    chosen = sorted((teams[p] for p in res.members), key=lambda c: c.members) if res.found else []
    result_teams = [Team(list(c.members), c.score, c.value_score, c.compat_score) for c in chosen]
    if result_teams:
        assert not validate_assignment(graph, tc, [t.members for t in result_teams]), "solver produced invalid assignment"
    assigned = {v for t in result_teams for v in t.members}
    finished = res.status == "optimal"
    proven = finished and bool(result_teams) and not info["restricted"]
    if proven:
        status = "optimal"
    elif finished and not result_teams and not info["restricted"]:
        status = "infeasible"
    else:
        status = "feasible_not_proven" if result_teams else "no_solution_found"
    out = MultiResult(status, proven, "search_completed" if finished else res.status, teams=result_teams,
                      unassigned=[v for v in range(n) if v not in assigned], total_score=sum(t.score for t in result_teams),
                      coverage=len(assigned), stats=stats_dict(), covered_by_some_team=covered)
    if status == "infeasible":
        out.issues = [{"code": "no_valid_assignment",
                       "message": "The search was exhaustive: no assignment satisfies all constraints on this compatibility graph.",
                       "suggestions": ["Lower the compatibility threshold", "Allow unassigned candidates",
                                       "Reduce the required team count or size", "Allow variable team sizes"]}]
    elif info["restricted"]:
        out.issues = [{"code": "team_graph_restricted",
                       "message": f"{len(every_team)} teams are possible, more than the {max_conflict_vertices} the team graph allows, so only each "
                                  "candidate's best teams were searched. The result is valid but not proven optimal.",
                       "suggestions": ["Raise the compatibility threshold to sparsify the graph", "Reduce team size or candidate count"]}]
    return out
