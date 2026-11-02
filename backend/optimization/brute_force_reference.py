"""Independent brute-force references (tiny instances only). They share no search code with the solvers."""
from __future__ import annotations
from itertools import combinations
from .models import Graph
from .constraints import TeamConstraints, validate_assignment, assignment_key


def brute_force_mwcp(graph: Graph, min_size: int = 1, max_size: int | None = None):
    n = graph.n
    max_size = n if max_size is None else min(max_size, n)
    best_s, best_m = None, []
    for k in range(min_size, max_size + 1):
        for c in combinations(range(n), k):
            if graph.is_clique(c):
                s = graph.score(c)
                if best_s is None or s > best_s + 1e-12:
                    best_s, best_m = s, list(c)
    return best_s, best_m


def brute_force_multi(graph: Graph, tc: TeamConstraints):
    """Enumerate every assignment of candidates to 'team label or unassigned'. Returns (key, teams) or (None, None)."""
    n = graph.n
    best = {"key": None, "teams": None}

    def go(v, teams):
        if len(teams) > tc.teams_max:
            return
        if v == n:
            ts = [list(t) for t in teams]
            if not validate_assignment(graph, tc, ts):
                k = assignment_key(graph, tc, ts)
                b = best["key"]
                if b is None or k[0] > b[0] or (k[0] == b[0] and k[1] > b[1] + 1e-12):
                    best["key"], best["teams"] = k, ts
            return
        for t in teams:
            if len(t) < tc.max_size:
                t.append(v)
                go(v + 1, teams)
                t.pop()
        teams.append([v])
        go(v + 1, teams)
        teams.pop()
        go(v + 1, teams)  # v unassigned (invalid terminal states are rejected by validate_assignment)

    go(0, [])
    return best["key"], best["teams"]
