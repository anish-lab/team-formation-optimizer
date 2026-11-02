"""Exact Branch-and-Bound for the (size-constrained) Maximum Weighted Clique Problem.

Maximises graph score (vertex weights + pairwise edge weights) over cliques with size in
[min_size, max_size].  With zero edge weights this is the classical vertex-weighted MWCP.
Bounds live in coloring_bound.py.  Colouring can be switched off; correctness is unchanged.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from .models import Graph
from .coloring_bound import bits, vertex_bounds, plain_upper_bound, coloring_upper_bound
from .statistics import SearchStats

EPS = 1e-12


class _Stop(Exception):
    def __init__(self, reason: str):
        self.reason = reason


@dataclass
class CliqueResult:
    members: list[int]
    score: float
    found: bool
    status: str            # optimal | infeasible | time_limit | node_limit | cancelled
    optimal: bool
    stats: SearchStats = field(default_factory=SearchStats)


def solve_clique(graph: Graph, min_size: int = 1, max_size: int | None = None, use_coloring: bool = True,
                 forced: int | None = None, allowed: int | None = None, time_limit: float | None = None,
                 node_limit: int | None = None, should_stop=None, validate: bool = True) -> CliqueResult:
    """Best clique with min_size <= |C| <= max_size, optionally containing `forced` and inside `allowed`."""
    if validate:
        graph.validate()
    n = graph.n
    if min_size < 0:
        raise ValueError("min_size must be >= 0")
    if max_size is not None and max_size < min_size:
        raise ValueError("max_size must be >= min_size")
    if forced is not None and not (0 <= forced < n):
        raise ValueError("forced vertex out of range")
    cap = n if max_size is None else min(max_size, n)
    full = (1 << n) - 1
    allowed = full if allowed is None else (allowed & full)
    stats = SearchStats()
    start = time.perf_counter()
    best = {"score": None, "members": []}

    def record(R, s):
        if len(R) >= min_size and (best["score"] is None or s > best["score"] + EPS):
            best["score"], best["members"] = s, list(R)
            stats.incumbent_updates += 1

    def expand(R, rs, P):
        stats.nodes += 1
        if should_stop is not None and should_stop():
            raise _Stop("cancelled")
        if node_limit is not None and stats.nodes > node_limit:
            raise _Stop("node_limit")
        if time_limit is not None and time.perf_counter() - start > time_limit:
            raise _Stop("time_limit")
        record(R, rs)
        m = cap - len(R)
        if m <= 0 or P == 0:
            return
        if len(R) + P.bit_count() < min_size:
            stats.pruned_by_feasibility += 1
            return
        verts = list(bits(P))
        b = vertex_bounds(graph, R, verts, m)
        ub = coloring_upper_bound(graph.adj, b, verts, m)[0] if use_coloring else plain_upper_bound(b, m)
        stats.bound_evaluations += 1
        if best["score"] is not None and rs + ub <= best["score"] + EPS:
            stats.pruned_by_bound += 1
            return
        order = sorted(verts, key=lambda v: (-b[v], v))
        rem = P
        for idx, v in enumerate(order):
            left = len(order) - idx
            if len(R) + left < min_size:
                stats.branches += left
                stats.pruned_by_feasibility += left
                break
            if best["score"] is not None:
                tail = sum(b[u] for u in order[idx: idx + m])
                if rs + tail <= best["score"] + EPS:
                    stats.branches += left
                    stats.pruned_by_bound += left
                    break
            stats.branches += 1
            gain = graph.vw[v] + sum(graph.ew[u][v] for u in R)
            expand(R + [v], rs + gain, rem & graph.adj[v])
            rem &= ~(1 << v)

    reason = None
    try:
        if forced is None:
            expand([], 0.0, allowed)
        else:
            expand([forced], graph.vw[forced], allowed & graph.adj[forced])
    except _Stop as s:
        reason = s.reason
    stats.runtime_s = time.perf_counter() - start
    found = best["score"] is not None
    if reason:
        return CliqueResult(best["members"], best["score"] or 0.0, found, reason, False, stats)
    return CliqueResult(best["members"], best["score"] or 0.0, found, "optimal" if found else "infeasible",
                        found, stats)
