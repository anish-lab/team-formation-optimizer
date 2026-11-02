"""Memory-bounded enumeration of all feasible team cliques, grouped by smallest vertex."""
from __future__ import annotations
from dataclasses import dataclass
from .models import Graph


class CliqueLimitExceeded(Exception):
    pass


@dataclass(frozen=True)
class TeamClique:
    members: tuple
    mask: int
    score: float
    value_score: float
    compat_score: float

    @property
    def size(self) -> int:
        return len(self.members)


def enumerate_cliques(graph: Graph, min_size: int, max_size: int, max_cliques: int = 250_000,
                      should_stop=None) -> list[list[TeamClique]]:
    """All cliques with max(min_size,1) <= size <= max_size; result[v] = cliques with smallest vertex v."""
    n = graph.n
    min_size = max(min_size, 1)
    out: list[list[TeamClique]] = [[] for _ in range(n)]
    count = 0

    def rec(R, mask, vs, cs, P):
        nonlocal count
        if len(R) >= min_size:
            count += 1
            if count > max_cliques:
                raise CliqueLimitExceeded(f"more than {max_cliques} feasible teams")
            if should_stop is not None and (count & 1023) == 0 and should_stop():
                raise CliqueLimitExceeded("stopped")
            out[R[0]].append(TeamClique(tuple(R), mask, vs + cs, vs, cs))
        if len(R) == max_size:
            return
        while P:
            low = P & -P
            v = low.bit_length() - 1
            P ^= low
            newP = P & graph.adj[v]
            if len(R) + 1 + newP.bit_count() < min_size:
                continue
            ce = sum(graph.ew[u][v] for u in R)
            rec(R + [v], mask | low, vs + graph.vw[v], cs + ce, newP)

    for v in range(n):
        P = graph.adj[v] & ~((1 << (v + 1)) - 1)
        if 1 + P.bit_count() < min_size or max_size < 1:
            continue
        rec([v], 1 << v, graph.vw[v], 0.0, P)
    return out
