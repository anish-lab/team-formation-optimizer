"""Weighted compatibility graph used by every solver.

Weights are *already scaled* by the objective (alpha, beta, normalisation), so the
score of a team C is simply  sum_{i in C} vw[i] + sum_{i<j in C} ew[i][j].
Both parts are non-negative. ew[i][j] must be 0 when (i, j) is not an edge.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass
class Graph:
    ids: list[str]
    vw: list[float]
    ew: list[list[float]]
    adj: list[int]  # bitmask adjacency (bit j of adj[i] set <=> edge i-j)
    raw_value: list[float] | None = None
    raw_compat: list[list[float]] | None = None

    @property
    def n(self) -> int:
        return len(self.ids)

    @property
    def has_edge_weights(self) -> bool:
        return any(x > 0 for row in self.ew for x in row)

    def is_edge(self, i: int, j: int) -> bool:
        return bool((self.adj[i] >> j) & 1)

    def is_clique(self, members) -> bool:
        m = list(members)
        return all(self.is_edge(m[a], m[b]) for a in range(len(m)) for b in range(a + 1, len(m)))

    def score_parts(self, members) -> tuple[float, float]:
        """Return (vertex_value_part, pairwise_compat_part) of a member list."""
        m = list(members)
        v = sum(self.vw[i] for i in m)
        c = sum(self.ew[m[a]][m[b]] for a in range(len(m)) for b in range(a + 1, len(m)))
        return v, c

    def score(self, members) -> float:
        v, c = self.score_parts(members)
        return v + c

    def validate(self) -> None:
        n = self.n
        if len(self.vw) != n or len(self.adj) != n or len(self.ew) != n:
            raise ValueError("Graph arrays have inconsistent lengths")
        for i in range(n):
            if len(self.ew[i]) != n:
                raise ValueError("Edge-weight matrix must be n x n")
            if not math.isfinite(self.vw[i]) or self.vw[i] < 0:
                raise ValueError(f"Vertex weight {i} must be finite and non-negative")
            if (self.adj[i] >> i) & 1:
                raise ValueError(f"Self loop at vertex {i}")
            for j in range(n):
                if self.is_edge(i, j) != self.is_edge(j, i):
                    raise ValueError(f"Adjacency not symmetric at ({i},{j})")
                w = self.ew[i][j]
                if not math.isfinite(w) or w < 0:
                    raise ValueError("Edge weights must be finite and non-negative")
                if abs(w - self.ew[j][i]) > 1e-12:
                    raise ValueError("Edge weights must be symmetric")
                if w > 0 and not self.is_edge(i, j):
                    raise ValueError("Positive edge weight on a non-edge")

    @classmethod
    def from_edges(cls, n, edges, vertex_weights=None, edge_weights=None, ids=None) -> "Graph":
        adj = [0] * n
        ew = [[0.0] * n for _ in range(n)]
        for (i, j) in edges:
            if i == j or not (0 <= i < n and 0 <= j < n):
                raise ValueError(f"Invalid edge ({i},{j})")
            adj[i] |= 1 << j
            adj[j] |= 1 << i
            w = float((edge_weights or {}).get((i, j), (edge_weights or {}).get((j, i), 0.0)))
            ew[i][j] = ew[j][i] = w
        g = cls(ids=ids or [str(i) for i in range(n)],
                vw=[float(x) for x in (vertex_weights if vertex_weights is not None else [1.0] * n)],
                ew=ew, adj=adj)
        g.validate()
        return g
