"""Reproducible comparison of BBMCW with parts of the paper's algorithm switched off, as in the paper's Section 4.5 (p. 27).

Run as a utility:  python -m evaluation.benchmark --random-n 16 --density 0.6 --seed 1
(The random-graph generator is an evaluation utility, kept separate from the user workflow.)
"""
from __future__ import annotations
import argparse
import json
import random
import statistics
from graph.metrics import graph_metrics
from optimization.bbmcw import solve_bbmcw
from optimization.constraints import TeamConstraints, resolve_constraints
from optimization.models import Graph
from optimization.team_conflict_solver import solve_teams_bbmcw

VARIANTS = (("BBMCW (full algorithm)", {}),
            ("BBMCW without MCOVER", {"use_mcover": False}),
            ("BBMCW without COVER and MCOVER", {"use_cover": False, "use_mcover": False}),
            ("BBMCW without AMTS", {"use_amts": False}))


def _cls(status: str) -> str:
    return {"optimal": "proven_optimum", "feasible_not_proven": "best_before_limit", "infeasible": "infeasible",
            "node_limit": "best_before_limit", "time_limit": "best_before_limit"}.get(status, status)


def _agg(vals):
    return {"mean": statistics.fmean(vals), "min": min(vals), "max": max(vals), "all": vals}


def run_comparison(graph: Graph, tc: TeamConstraints, time_limit: float = 20.0, node_limit: int | None = None,
                   max_cliques: int = 250_000, repeats: int = 3) -> dict:
    rows = []
    for name, switches in VARIANTS:
        times, last = [], None
        for _ in range(repeats):
            last = solve_teams_bbmcw(graph, tc, time_limit, node_limit, max_cliques, **switches)
            times.append(last.stats.get("total_runtime_s", 0.0))
        st = last.stats
        rows.append({"algorithm": name, "status": last.status, "guarantee": _cls(last.status), "runtime_s": _agg(times),
                     "objective": last.total_score, "nodes": st.get("nodes", 0), "branches": st.get("branches", 0),
                     "pruned_by_bound": st.get("pruned_by_bound", 0), "pruned_by_feasibility": st.get("pruned_by_feasibility", 0),
                     "pruning_efficiency": st.get("pruning_efficiency", 0.0), "team_graph_vertices": st.get("team_graph_vertices", 0),
                     "teams": len(last.teams), "coverage": last.coverage, "team_sizes": sorted(len(t.members) for t in last.teams),
                     "feasible": bool(last.teams), "optimality_proven": last.optimality_proven})
    notes = ["Every row is the paper's BBMCW. Rows differ only by which parts are switched off, as in the paper's Section 4.5.",
             "Only compare guarantees between rows with the same status: a proven optimum and a best-before-limit result are not equal."]
    return {"graph": graph_metrics(graph), "constraints": tc.to_dict(), "repeats": repeats, "rows": rows, "notes": notes,
            "vertex_weighted": run_vertex_weighted_comparison(graph, min(time_limit, 20.0), repeats)}


def run_vertex_weighted_comparison(graph: Graph, time_limit: float = 20.0, repeats: int = 3) -> dict:
    """The paper's own problem on the candidate graph: candidate values only, no team rules or pairwise weights."""
    rows = []
    for name, switches in VARIANTS:
        times, last = [], None
        for _ in range(repeats):
            last = solve_bbmcw(graph.vw, graph.adj, time_limit=time_limit, **switches)
            times.append(last.stats.runtime_s)
        rows.append({"algorithm": name, "status": last.status, "guarantee": _cls(last.status), "runtime_s": _agg(times),
                     "nodes": last.stats.nodes, "branches": last.stats.branches, "pruned_by_bound": last.stats.pruned_by_bound,
                     "objective": last.weight, "clique_size": len(last.members)})
    return {"rows": rows, "note": "Vertex weights only, on the candidate graph, with no team rules: the problem exactly as the paper states it."}


def random_graph(n: int, density: float, seed: int) -> Graph:
    rng = random.Random(seed)
    edges, ew = [], {}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < density:
                edges.append((i, j))
                ew[(i, j)] = rng.random()
    return Graph.from_edges(n, edges, [rng.random() for _ in range(n)], ew)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--random-n", type=int, default=14)
    ap.add_argument("--density", type=float, default=0.6)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--team-size", type=int, default=3)
    ap.add_argument("--teams", type=int, default=3)
    ap.add_argument("--repeats", type=int, default=3)
    a = ap.parse_args()
    g = random_graph(a.random_n, a.density, a.seed)
    tc = resolve_constraints(g.n, {"policy": "leave_unassigned", "preferred_size": a.team_size, "num_teams": a.teams})
    print(json.dumps(run_comparison(g, tc, repeats=a.repeats), indent=2, default=str))


if __name__ == "__main__":
    main()
