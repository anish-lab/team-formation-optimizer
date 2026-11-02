"""Result serialisation and export helpers."""
from __future__ import annotations
import csv
import io
import json
from graph.builder import BuiltGraph
from graph.metrics import graph_metrics
from optimization.constraints import TeamConstraints, validate_assignment

MAX_EDGES_RETURNED = 3000


def build_result(built: BuiltGraph, tc: TeamConstraints, res, heuristic: bool = False, violations=None) -> dict:
    g, obj = built.graph, built.objective
    teams = []
    for k, t in enumerate(res.teams):
        v = validate_assignment(g, tc, [x.members for x in res.teams])
        teams.append({"team": k + 1, "size": len(t.members),
                      "members": [{"id": g.ids[i], "index": i, "value": g.raw_value[i]} for i in t.members],
                      "score": t.score, "value_score": t.value_score, "compat_score": t.compat_score,
                      "mean_pair_compat": (sum(g.raw_compat[a][b] for x, a in enumerate(t.members) for b in t.members[x + 1:]) /
                                           (len(t.members) * (len(t.members) - 1) / 2)) if len(t.members) > 1 else None,
                      "satisfies_hard_constraints": not v, "feature_contributions": built.team_breakdown(t.members)})
    covered = res.covered_by_some_team or []
    una = []
    for i in res.unassigned:
        deg = g.adj[i].bit_count()
        if covered and not covered[i]:
            reason = "No feasible team (a clique within the size limits) contains this candidate."
        else:
            reason = "Not selected in the returned assignment; the solver does not attribute a specific cause."
        una.append({"id": g.ids[i], "index": i, "compatible_candidates": deg, "reason": reason})
    team_of = {i: k for k, t in enumerate(res.teams) for i in t.members}
    keep = sorted(((g.raw_compat[i][j], i, j) for i in range(g.n) for j in range(i + 1, g.n) if g.is_edge(i, j)), reverse=True)
    intra = {(i, j) for t in res.teams for a, i in enumerate(t.members) for j in t.members[a + 1:]}
    edges = [{"source": g.ids[i], "target": g.ids[j], "compat": c, "intra_team": (i, j) in intra}
             for c, i, j in keep[:MAX_EDGES_RETURNED]]
    if len(keep) > MAX_EDGES_RETURNED:
        have = {(e["source"], e["target"]) for e in edges}
        edges += [{"source": g.ids[i], "target": g.ids[j], "compat": g.raw_compat[i][j], "intra_team": True}
                  for (i, j) in intra if (g.ids[i], g.ids[j]) not in have]
    vsum = sum(t.value_score for t in res.teams)
    csum = sum(t.compat_score for t in res.teams)
    return {
        "status": res.status, "optimality_proven": res.optimality_proven, "heuristic": heuristic,
        "termination_reason": res.termination_reason, "issues": res.issues, "violations": violations or [],
        "objective": {"formula": "TeamScore(C) = alpha*sum(w_i)/k_ref + beta*sum_{i<j} c_ij/C(k_ref,2); total = sum over teams",
                      **obj.to_dict(), "priority": tc.priority,
                      "priority_explained": ("lexicographic: (1) hard constraints, (2) number of assigned candidates, (3) total team score, (4) deterministic first-found tie-break"
                                             if tc.priority == "coverage_first" else
                                             "lexicographic: (1) hard constraints, (2) total team score, (3) deterministic first-found tie-break")},
        "constraints": tc.to_dict(),
        "summary": {"teams": len(res.teams), "assigned": res.coverage, "unassigned": len(res.unassigned),
                    "team_sizes": [len(t.members) for t in res.teams], "total_score": res.total_score,
                    "value_contribution": vsum, "compat_contribution": csum,
                    "runtime_s": res.stats.get("total_runtime_s", 0.0)},
        "teams": teams, "unassigned": una, "stats": res.stats, "graph_metrics": graph_metrics(g), "warnings": built.warnings,
        "graph": {"nodes": [{"id": g.ids[i], "value": g.raw_value[i], "team": team_of.get(i)} for i in range(g.n)], "edges": edges,
                  "edges_truncated": len(keep) > MAX_EDGES_RETURNED},
    }


def teams_csv(result: dict) -> str:
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(["team", "candidate_id", "team_size", "team_score"])
    for t in result["teams"]:
        for m in t["members"]:
            w.writerow([t["team"], m["id"], t["size"], f"{t['score']:.6f}"])
    return b.getvalue()


def unassigned_csv(result: dict) -> str:
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(["candidate_id", "compatible_candidates", "reason"])
    for u in result["unassigned"]:
        w.writerow([u["id"], u["compatible_candidates"], u["reason"]])
    return b.getvalue()


def summary_text(result: dict, config: dict) -> str:
    s, o = result["summary"], result["objective"]
    guarantee = ("PROVEN OPTIMUM for the stated objective and constraints" if result["optimality_proven"] else
                 "HEURISTIC solution (no optimality guarantee)" if result["heuristic"] else
                 "Best solution found; optimality NOT proven" if result["teams"] else f"No solution ({result['status']})")
    lines = ["Team formation experiment summary", "=" * 34, f"Status: {result['status']} - {guarantee}",
             f"Termination reason: {result['termination_reason']}", "",
             f"Objective: {o['formula']}", f"alpha={o['alpha']} beta={o['beta']} edge_mode={o['edge_mode']} threshold={o['threshold']} k_ref={o['preferred_size']}",
             f"Priority: {o['priority_explained']}", "",
             f"Teams formed: {s['teams']} (sizes {s['team_sizes']}); assigned {s['assigned']}, unassigned {s['unassigned']}",
             f"Total score: {s['total_score']:.6f} (value part {s['value_contribution']:.6f}, compatibility part {s['compat_contribution']:.6f})",
             f"Runtime: {s['runtime_s']:.3f}s; search nodes {result['stats'].get('nodes')}, pruned by bound {result['stats'].get('pruned_by_bound')}",
             f"Algorithm: {result['stats'].get('algorithm', 'greedy heuristic')}; possible teams in the team graph: {result['stats'].get('team_graph_vertices', 'n/a')}",
             "", "Configuration (for reproducibility):", json.dumps(config, indent=2)]
    return "\n".join(lines)
