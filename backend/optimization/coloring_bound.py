"""Weighted colouring-based upper bound for clique search.

Search state: current clique R, candidate set P (vertices adjacent to all of R),
remaining capacity m = max_size - |R|.  For any clique S subset of P with |S| <= m:

    gain(S) = sum_{v in S} (vw[v] + sum_{u in R} ew[u][v]) + sum_{ {u,v} subset S } ew[u][v].

Per-vertex bound (each pair term split half/half between its endpoints):

    b_v = vw[v] + sum_{u in R} ew[u][v] + 1/2 * (sum of the (m-1) largest ew[v][u], u in P, u != v)

Since |S| <= m, v has at most m-1 partners inside S, hence gain(S) <= sum_{v in S} b_v.

Colouring: a *proper* greedy colouring of the graph induced by P partitions P into independent
classes (no two vertices in a class are adjacent).  A clique holds at most one vertex per class
and at most m vertices overall, so

    gain(S) <= sum of the m largest class maxima   (class maximum = max_{v in class} b_v).

Without colouring the valid bound is the sum of the m largest b_v; the colouring bound is never
larger (class maxima are a subset of the b values).  Both are valid upper bounds, so pruning
with either never removes an optimal solution.  This adapts the colouring idea used for weighted
clique search; it is NOT a reproduction of the BBMCW algorithm of San Segundo et al.
"""
from __future__ import annotations
from .models import Graph


def bits(mask: int):
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


def greedy_coloring(adj: list[int], order: list[int]) -> list[list[int]]:
    """Sequential greedy colouring; returns independent classes (a proper colouring)."""
    uncolored = list(order)
    classes: list[list[int]] = []
    while uncolored:
        cls, blocked, rest = [], 0, []
        for v in uncolored:
            if (blocked >> v) & 1:
                rest.append(v)
            else:
                cls.append(v)
                blocked |= adj[v]
        classes.append(cls)
        uncolored = rest
    return classes


def vertex_bounds(graph: Graph, R: list[int], verts: list[int], m: int) -> dict[int, float]:
    has_ew = graph.has_edge_weights if m > 1 else False
    b: dict[int, float] = {}
    for v in verts:
        val = graph.vw[v] + sum(graph.ew[u][v] for u in R)
        if has_ew:
            row = graph.ew[v]
            partners = sorted((row[u] for u in verts if u != v), reverse=True)[: m - 1]
            val += 0.5 * sum(partners)
        b[v] = val
    return b


def top_m_sum(values, m: int) -> float:
    return float(sum(sorted(values, reverse=True)[: max(m, 0)]))


def plain_upper_bound(b: dict[int, float], m: int) -> float:
    return top_m_sum(b.values(), m)


def coloring_upper_bound(adj: list[int], b: dict[int, float], verts: list[int], m: int):
    order = sorted(verts, key=lambda v: (-b[v], v))
    classes = greedy_coloring(adj, order)
    maxima = [max(b[v] for v in cls) for cls in classes]
    return top_m_sum(maxima, m), classes
