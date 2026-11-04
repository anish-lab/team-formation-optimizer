"""Build the weighted compatibility graph from a validated table.

Candidate value   w_i  = sum_f imp_f * value_f(i) / sum_f imp_f   over features whose role includes 'value'  (in [0,1])
Compatibility     c_ij = sum_f imp_f * pair_f(i,j) / sum_f imp_f over features whose role includes 'compat' (in [0,1])
                         (c_ij = 1 for all pairs if no feature feeds compatibility)
Edge rule         'hard': edge iff c_ij >= threshold (non-edges can never share a team)
                  'soft': complete graph, c_ij is only a quality weight
Objective         TeamScore(C) = alpha * (sum_{i in C} w_i) / k_ref  +  beta * (sum_{i<j in C} c_ij) / C(k_ref,2)
                  where k_ref = preferred team size.  For a team of k_ref members this equals
                  alpha*mean value + beta*mean pairwise compatibility, so both terms live on a [0,1] scale.
Note: in 'hard' mode the compatibility score both decides edges and contributes to the objective (documented
double use); set beta = 0 to use it purely as a constraint.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import comb
from data.feature_schema import FeatureDef
from data.validation import ParsedTable
from optimization.models import Graph
from .compatibility import value_score, pair_score, matrix_lookup


@dataclass
class ObjectiveConfig:
    alpha: float = 1.0
    beta: float = 1.0
    edge_mode: str = "hard"
    threshold: float = 0.5
    preferred_size: int = 4

    def to_dict(self):
        return self.__dict__.copy()


@dataclass
class BuiltGraph:
    graph: Graph
    table: ParsedTable
    objective: ObjectiveConfig
    warnings: list[str]


def build_graph(table: ParsedTable, obj: ObjectiveConfig) -> BuiltGraph:
    feats = table.features
    n = len(table.ids)
    warnings: list[str] = []
    for f in feats:  # matrix completeness (no silently invented entries)
        if f.compat_method == "matrix" and f.uses_compat:
            cats = table.stats[f.name]["categories"]
            for a in cats:
                for b in cats:
                    matrix_lookup(f, a, b)
    vf = [f for f in feats if f.uses_value]
    cf = [f for f in feats if f.uses_compat]
    vtot, ctot = sum(f.importance for f in vf), sum(f.importance for f in cf)
    if not vf:
        warnings.append("No feature feeds candidate value: all candidate values are 0 (only compatibility is optimised).")
    if not cf:
        warnings.append("No feature feeds compatibility: every pair has compatibility 1 (complete graph).")
    raw_v = [sum(f.importance * value_score(f, table.values[f.name][i], table.stats[f.name]) for f in vf) / vtot if vf else 0.0
             for i in range(n)]
    raw_c = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            c = sum(f.importance * pair_score(f, table.values[f.name][i], table.values[f.name][j], table.stats[f.name])
                    for f in cf) / ctot if cf else 1.0
            raw_c[i][j] = raw_c[j][i] = c
    k = max(obj.preferred_size, 1)
    vscale = obj.alpha / k
    escale = obj.beta / max(comb(k, 2), 1)
    adj = [0] * n
    ew = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if obj.edge_mode == "soft" or raw_c[i][j] >= obj.threshold - 1e-12:
                adj[i] |= 1 << j
                adj[j] |= 1 << i
                ew[i][j] = ew[j][i] = escale * raw_c[i][j]
    g = Graph(ids=list(table.ids), vw=[vscale * x for x in raw_v], ew=ew, adj=adj, raw_value=raw_v, raw_compat=raw_c)
    g.validate()
    return BuiltGraph(g, table, obj, warnings)
