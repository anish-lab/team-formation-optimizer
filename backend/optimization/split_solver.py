"""Big groups: too many possible teams for one team graph, so re-solve a few teams at a time with AMTS and BBMCW.

40 people in teams of 5 have 658 008 possible teams, far above what one team graph can hold.  Instead:
  1. Start from a valid split of the people into teams (a shuffled list cut into teams).
  2. Take a few teams, and solve just their members exactly as a small problem with solve_teams_bbmcw.
  3. Keep the new teams if they score higher, and repeat until no group of teams can improve or time runs out.

Not from the paper: this splitting.  Every team still comes from the paper's algorithms, but the overall answer is
only the best found, so it is always reported as feasible_not_proven.
"""
from __future__ import annotations
import itertools
import math
import random
import time
from .constraints import TeamConstraints, check_feasibility, validate_assignment
from .models import Graph
from .team_conflict_solver import MultiResult, Team, solve_teams_bbmcw

ALGORITHM = "bbmcw_split"
TEAMS_LIMIT = 20_000        # above this many possible teams, one team graph is not used
MAX_SUB_TEAMS = 4           # teams re-solved together
MAX_SUB_VERTICES = 15_000   # possible teams in one small problem
SUB_TIME_LIMIT = 2.0
SEED = 0
EPS = 1e-9


def possible_teams(n: int, tc: TeamConstraints) -> int:
    return sum(math.comb(n, s) for s in range(tc.min_size, tc.max_size + 1))


def _start_sizes(n: int, tc: TeamConstraints) -> list[int]:
    """The team sizes to use.  The most teams allowed, with sizes differing by at most one."""
    for t in range(tc.teams_max, tc.teams_min - 1, -1):
        if t * tc.min_size <= n and (not tc.full_coverage or n <= t * tc.max_size):
            if tc.equal_sizes:
                return [tc.min_size] * t
            base, extra = max(n // t, tc.min_size), max(n - t * max(n // t, tc.min_size), 0)
            return [base + (i < extra) for i in range(t)]
    return []


def _sub_team_count(n: int, sizes: list[int], tc: TeamConstraints) -> int:
    """The most teams that can be re-solved together while the small problem stays small.  0 = none can."""
    spare = n - sum(sizes)
    for m in range(min(MAX_SUB_TEAMS, len(sizes)), 1, -1):
        if possible_teams(m * max(sizes) + spare, tc) <= MAX_SUB_VERTICES:
            return m
    return 0


def can_split(graph: Graph, tc: TeamConstraints) -> bool:
    """Split only when one team graph cannot hold every team, anyone can join anyone, and the size rules are simple."""
    n = graph.n
    if possible_teams(n, tc) <= TEAMS_LIMIT or check_feasibility(n, tc) or tc.max_short_teams is not None:
        return False
    if not (tc.full_coverage or tc.equal_sizes) or any(a.bit_count() != n - 1 for a in graph.adj):
        return False
    sizes = _start_sizes(n, tc)
    return bool(sizes) and _sub_team_count(n, sizes, tc) > 0


def _induced(graph: Graph, members: list[int]) -> Graph:
    pos = {v: i for i, v in enumerate(members)}
    adj = [sum(1 << pos[u] for u in members if (graph.adj[v] >> u) & 1) for v in members]
    return Graph(ids=[graph.ids[v] for v in members], vw=[graph.vw[v] for v in members],
                 ew=[[graph.ew[a][b] for b in members] for a in members], adj=adj)


def solve_by_splitting(graph: Graph, tc: TeamConstraints, time_limit: float | None = None, should_stop=None,
                       progress: dict | None = None, seed: int = SEED, sub_teams: int | None = None) -> MultiResult:
    t0 = time.perf_counter()
    progress = progress if progress is not None else {}
    stop = should_stop or (lambda: False)
    out_of_time = lambda: stop() or (time_limit is not None and time.perf_counter() - t0 >= time_limit)
    rng = random.Random(seed)
    n = graph.n
    sizes = _start_sizes(n, tc)
    people = list(range(n))
    rng.shuffle(people)
    teams, cut = [], 0
    for s in sizes:
        teams.append(sorted(people[cut:cut + s]))
        cut += s
    spare = people[cut:]
    top = sub_teams or _sub_team_count(n, sizes, tc)
    settled: set[frozenset] = set()                            # groups of teams already known not to improve
    solved = 0

    def key(group) -> frozenset:
        return frozenset(tuple(teams[i]) for i in group) | {tuple(sorted(spare))}

    # Two teams at a time settles in under a second, then larger groups use the remaining time.
    for m in ([top] if sub_teams else range(2, top + 1)):
        sub_tc = TeamConstraints(tc.min_size, tc.max_size, m, m, tc.full_coverage, tc.equal_sizes, tc.preferred_size, None,
                                 tc.priority, tc.policy)
        while not out_of_time():
            groups = list(itertools.combinations(range(len(teams)), m))
            rng.shuffle(groups)
            for group in groups:
                if out_of_time():
                    break
                if key(group) in settled:
                    continue
                members = sorted(v for i in group for v in teams[i]) + sorted(spare)
                left = SUB_TIME_LIMIT if time_limit is None else min(SUB_TIME_LIMIT, time_limit - (time.perf_counter() - t0))
                res = solve_teams_bbmcw(_induced(graph, members), sub_tc, left, should_stop=stop)
                solved += 1
                now = sum(graph.score(teams[i]) for i in group)
                if res.teams and res.total_score > now + EPS:
                    new = [sorted(members[p] for p in t.members) for t in res.teams]
                    for i, t in zip(group, new):
                        teams[i] = t
                    used = {v for t in new for v in t}
                    spare = [v for v in members if v not in used]
                elif res.optimality_proven:
                    settled.add(key(group))
            progress.update(sub_problems_solved=solved)
            if all(key(g) in settled for g in groups):
                break                                          # no group of this size can improve
    assert not validate_assignment(graph, tc, teams), "split solver produced invalid assignment"
    result = []
    for t in sorted(teams):
        value, compat = graph.score_parts(t)
        result.append(Team(t, value + compat, value, compat))
    return MultiResult("feasible_not_proven", False, "search_completed", teams=result, unassigned=sorted(spare),
                       total_score=sum(t.score for t in result), coverage=sum(len(t) for t in teams),
                       stats={"algorithm": ALGORITHM, "sub_problems_solved": solved, "total_runtime_s": time.perf_counter() - t0})
