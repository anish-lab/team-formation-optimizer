"""Reproducible comparison: exact solver (colouring on/off), greedy baseline, brute force (tiny n).

Run as a utility:  python -m evaluation.benchmark --random-n 16 --density 0.6 --seed 1
(The random-graph generator is an evaluation utility, kept separate from the user workflow.)
"""
from __future__ import annotations
import argparse
import json
import random
import statistics
import time
from graph.metrics import graph_metrics
from optimization.models import Graph
from optimization.constraints import TeamConstraints, resolve_constraints, validate_assignment, assignment_key
from optimization.mwcp_solver import solve_clique
from optimization.multi_team_solver import solve_multi_team
from optimization.greedy_baseline import greedy_teams
from optimization.brute_force_reference import brute_force_multi
from optimization.bbmcw import solve_bbmcw
from optimization.team_conflict_solver import solve_teams_bbmcw

BRUTE_FORCE_MAX_N = 9


def _cls(status: str) -> str:
    return {"optimal": "proven_optimum", "feasible_not_proven": "best_before_limit", "heuristic": "heuristic",
            "infeasible": "infeasible", "node_limit": "best_before_limit", "time_limit": "best_before_limit"}.get(status, status)


def _agg(vals):
    return {"mean": statistics.fmean(vals), "min": min(vals), "max": max(vals), "all": vals}


def run_comparison(graph: Graph, tc: TeamConstraints, time_limit: float = 20.0, node_limit: int | None = None,
                   max_cliques: int = 250_000, repeats: int = 3) -> dict:
    rows = []
    gm = graph_metrics(graph)

    def base(name, coloring, status, **kw):
        row = {"algorithm": name, "coloring": coloring, "status": status, "guarantee": _cls(status)}
        row.update(kw)
        rows.append(row)

    for col in (True, False):  # single best team (the pure size-constrained MWCP)
        times, last = [], None
        for _ in range(repeats):
            r = solve_clique(graph, tc.min_size, tc.max_size, col, time_limit=time_limit, node_limit=node_limit)
            times.append(r.stats.runtime_s)
            last = r
        base("mwcp_single_team", col, last.status, runtime_s=_agg(times), objective=last.score, nodes=last.stats.nodes,
             branches=last.stats.branches, pruned_by_bound=last.stats.pruned_by_bound,
             pruned_by_feasibility=last.stats.pruned_by_feasibility, pruning_efficiency=last.stats.to_dict()["pruning_efficiency"],
             teams=1 if last.found else 0, coverage=len(last.members), team_sizes=[len(last.members)] if last.found else [], feasible=last.found)
    times, last = [], None  # the app's team solver: BBMCW on the team graph
    for _ in range(repeats):
        r = solve_teams_bbmcw(graph, tc, time_limit, node_limit, max_cliques)
        times.append(r.stats.get("total_runtime_s", 0.0))
        last = r
    st = last.stats
    base("bbmcw_team_graph", None, last.status, runtime_s=_agg(times), objective=last.total_score,
         nodes=st.get("nodes", 0), branches=st.get("branches", 0), pruned_by_bound=st.get("pruned_by_bound", 0),
         pruned_by_feasibility=st.get("pruned_by_feasibility", 0), pruning_efficiency=st.get("pruning_efficiency", 0.0),
         team_graph_vertices=st.get("team_graph_vertices", 0), teams=len(last.teams), coverage=last.coverage,
         team_sizes=sorted(len(t.members) for t in last.teams), feasible=bool(last.teams), optimality_proven=last.optimality_proven)
    for col in (True, False):  # joint multi-team exact optimisation (previous team solver, kept for comparison)
        times, last = [], None
        for _ in range(repeats):
            r = solve_multi_team(graph, tc, col, time_limit, node_limit, max_cliques)
            times.append(r.stats.get("total_runtime_s", 0.0))
            last = r
        st = last.stats
        m = st.get("mwcp_phase", {})
        base("multi_team_exact", col, last.status, runtime_s=_agg(times), objective=last.total_score,
             nodes=st.get("nodes", 0), branches=st.get("branches", 0), pruned_by_bound=st.get("pruned_by_bound", 0),
             pruned_by_feasibility=st.get("pruned_by_feasibility", 0), pruning_efficiency=st.get("pruning_efficiency", 0.0),
             mwcp_phase_nodes=m.get("nodes", 0), mwcp_phase_pruned_by_bound=m.get("pruned_by_bound", 0),
             teams=len(last.teams), coverage=last.coverage, team_sizes=sorted(len(t.members) for t in last.teams),
             feasible=bool(last.teams), optimality_proven=last.optimality_proven)
    t0 = time.perf_counter()
    gr, viol = greedy_teams(graph, tc)
    base("greedy_baseline", None, "heuristic", runtime_s=_agg([time.perf_counter() - t0]), objective=gr.total_score,
         nodes=gr.stats.get("nodes", 0), teams=len(gr.teams), coverage=gr.coverage,
         team_sizes=sorted(len(t.members) for t in gr.teams), feasible=not viol, violations=viol)
    if graph.n <= BRUTE_FORCE_MAX_N:
        t0 = time.perf_counter()
        key, teams = brute_force_multi(graph, tc)
        base("brute_force", None, "optimal" if teams else "infeasible", runtime_s=_agg([time.perf_counter() - t0]),
             objective=key[1] if key else 0.0, teams=len(teams or []), coverage=sum(map(len, teams or [])),
             team_sizes=sorted(map(len, teams or [])), feasible=bool(teams))
    notes = ["Colouring is not guaranteed to reduce runtime; compare the measured rows.",
             "Greedy is a heuristic without optimality guarantee; its objective is not comparable to a proven optimum on equal terms.",
             f"Brute force only runs for n <= {BRUTE_FORCE_MAX_N}."]
    vw = run_vertex_weighted_comparison(graph, min(time_limit, 20.0), repeats)
    return {"graph": gm, "constraints": tc.to_dict(), "repeats": repeats, "rows": rows, "notes": notes, "vertex_weighted": vw}


def run_vertex_weighted_comparison(graph: Graph, time_limit: float = 20.0, repeats: int = 3) -> dict:
    """Classical vertex-weighted MWCP (candidate values only, no size limits, no pair weights):
    paper-style BBMCW vs this project's adapted solver with colouring on/off."""
    vg = Graph(ids=graph.ids, vw=list(graph.vw), ew=[[0.0] * graph.n for _ in range(graph.n)], adj=list(graph.adj))
    rows = []
    for name, fn in (("paper_bbmcw", lambda: solve_bbmcw(vg.vw, vg.adj, time_limit=time_limit)),
                     ("adapted_coloring_on", lambda: solve_clique(vg, 1, None, True, time_limit=time_limit, validate=False)),
                     ("adapted_coloring_off", lambda: solve_clique(vg, 1, None, False, time_limit=time_limit, validate=False))):
        times, last = [], None
        for _ in range(repeats):
            last = fn()
            times.append(last.stats.runtime_s)
        score = getattr(last, "weight", None)
        score = last.score if score is None else score
        rows.append({"algorithm": name, "status": last.status, "guarantee": _cls(last.status), "runtime_s": _agg(times),
                     "nodes": last.stats.nodes, "branches": last.stats.branches, "pruned_by_bound": last.stats.pruned_by_bound,
                     "objective": score, "clique_size": len(last.members)})
    return {"rows": rows, "note": "Vertex weights only, on the candidate graph (no team-size limits, no pairwise weights). This compares the "
            "algorithms on the classical problem; the bbmcw_team_graph row above is how BBMCW handles those rules for team formation."}


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
