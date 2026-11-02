from __future__ import annotations
import statistics
from optimization.models import Graph


def graph_metrics(g: Graph) -> dict:
    n = g.n
    deg = [g.adj[i].bit_count() for i in range(n)]
    edges = sum(deg) // 2
    dens = edges / (n * (n - 1) / 2) if n > 1 else 0.0
    warnings = []
    if n > 1 and dens < 0.05:
        warnings.append("Graph is very sparse (density < 5%): few or no feasible teams. Consider lowering the threshold.")
    if n > 1 and dens > 0.95:
        warnings.append("Graph is nearly complete (density > 95%): the threshold barely constrains teams and exact search may be slow.")
    return {"vertices": n, "edges": edges, "density": dens,
            "degree": {"min": min(deg, default=0), "max": max(deg, default=0),
                       "mean": statistics.fmean(deg) if deg else 0.0, "median": statistics.median(deg) if deg else 0.0},
            "isolated_vertices": sum(d == 0 for d in deg), "warnings": warnings}
