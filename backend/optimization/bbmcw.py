"""BBMCW-style exact solver for the (vertex-weighted) Maximum Weighted Clique Problem.

Implemented from the algorithm description in:
  P. San Segundo, F. Furini, J. Artieda, "A new branch-and-bound algorithm for the Maximum Weighted Clique
  Problem", Computers & Operations Research 110 (2019) 18-33.
Reference points (paper section): Branching Set / Pruned Set scheme (2), Covering Bound with loads (2.1, eq. 9-12),
splitting rules R1/R2/R3 (2.1), COLOR (Alg. 1), COVER (Alg. 2), MCOVER (Alg. 3), GenBranchSet (Alg. 4), BBMCW (Alg. 5).

Faithfulness notes (what is and is not the paper's algorithm):
  * Same: partial greedy colouring with loads, gap-budgeted insertion, R1/R2/R3 splitting in COVER, multi-set MCOVER,
    Branching Set B / Pruned Set P, branching only on B in order of non-increasing weight, degeneracy initial ordering
    (min degree last, ties by smaller weight), bitset graph.
  * Different / not implemented: the initial incumbent comes from a simple greedy heuristic instead of AMTS tabu search;
    the colour-sort alternative ordering and the "max 3 vertices per independent set" optimisation are not implemented.
  * The printed gap update of MCOVER in the extracted text looks garbled; here the gap is always recomputed as
    budget - (sum of set maxima + implicit singleton loads), which is the quantity the paper's bound (12) defines.
  * In Alg. 5 the child gap uses w(C + b); this implementation uses that (correct) clique weight.
Correctness does not rest on the paper's text: tests compare the result with brute force and check the Pruned-Set
property omega(G[P]) <= lb - w(C) on every Branching-Set computation.
Scope: vertex weights only (no edge weights, no size limits) - exactly the classical MWCP.

Optional extensions used by team_conflict_solver.py (all off by default, so the classical behaviour is unchanged).
None of them is in the paper; none changes the bound or the Branching/Pruned Set computation:
  * accept(clique): only accepted cliques may become the incumbent.  Safe, because pruning only ever discards cliques
    that cannot beat the incumbent, whether or not they would be accepted.
  * restrict(clique, V, budget): may remove from V vertices that cannot lead to an accepted, improving clique.
  * initial: a starting incumbent supplied by the caller; preordered: keep the caller's vertex order.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from .coloring_bound import bits
from .statistics import SearchStats

EPS = 1e-9


class _Stop(Exception):
    def __init__(self, reason):
        self.reason = reason


@dataclass
class BBMCWResult:
    members: list[int]
    weight: float
    status: str  # optimal | time_limit | node_limit | cancelled
    optimal: bool
    stats: SearchStats = field(default_factory=SearchStats)
    found: bool = True


def degeneracy_order(weights, adj) -> list[int]:
    """order[new_index] = old_index. Min-degree vertex goes LAST (ties: smaller weight), repeatedly."""
    n = len(weights)
    remaining = (1 << n) - 1
    order = [0] * n
    for pos in range(n - 1, -1, -1):
        best = None
        for v in bits(remaining):
            key = ((adj[v] & remaining).bit_count(), weights[v], v)
            if best is None or key < best[0]:
                best = (key, v)
        order[pos] = best[1]
        remaining &= ~(1 << best[1])
    return order


def greedy_clique(w, adj):
    best, bw = [], 0.0
    for s in sorted(range(len(w)), key=lambda v: -w[v]):
        C, cand = [s], adj[s]
        while cand:
            u = max(bits(cand), key=lambda x: (w[x], -x))
            C.append(u)
            cand &= adj[u]
        cw = sum(w[x] for x in C)
        if cw > bw + EPS:
            best, bw = C, cw
    return best, bw


def solve_bbmcw(weights: list[float], adj: list[int], time_limit: float | None = None, node_limit: int | None = None,
                should_stop=None, hook=None, accept=None, restrict=None, initial: list[int] | None = None,
                preordered: bool = False, validate: bool = True, on_incumbent=None,
                stats: SearchStats | None = None) -> BBMCWResult:
    n = len(weights)
    if len(adj) != n or any(x < 0 or x != x for x in weights):
        raise ValueError("weights must be finite and non-negative, adj must have one mask per vertex")
    if validate:
        for i in range(n):
            if (adj[i] >> i) & 1 or any(((adj[i] >> j) & 1) != ((adj[j] >> i) & 1) for j in range(n)):
                raise ValueError("adjacency must be symmetric without self loops")
    stats = SearchStats() if stats is None else stats
    t0 = time.perf_counter()
    if n == 0:
        return BBMCWResult([], 0.0, "optimal", True, stats, accept is None)
    if preordered:
        order, w, A = list(range(n)), [float(x) for x in weights], adj
    else:
        order = degeneracy_order(weights, adj)                 # preprocessing (Section 2.5)
        inv = {old: new for new, old in enumerate(order)}
        w = [float(weights[order[i]]) for i in range(n)]
        A = [sum(1 << inv[j] for j in bits(adj[order[i]])) for i in range(n)]
    if initial is not None:
        inc = [inv[v] for v in initial] if not preordered else list(initial)
        lb = sum(w[v] for v in inc)
    elif accept is None:
        inc, lb = greedy_clique(w, A)                          # initial incumbent (paper: AMTS)
    else:
        inc, lb = None, -1.0                                   # no accepted clique known yet: nothing can be pruned
    best = {"C": None if inc is None else list(inc), "w": lb}

    def gen_branch_set(V: int, budget: float) -> list[int]:
        """Algorithm 4 (GenBranchSet): returns Branching Set B (sorted by non-increasing weight)."""
        if budget < 0:
            return sorted(bits(V), key=lambda x: (-w[x], x))
        # ---- COLOR (Algorithm 1): partial greedy colouring with gap budget ----
        Brest, ub, classes = V, 0.0, []
        while True:
            Bk, I, lhat = Brest, [], 0.0
            while Bk:
                low = Bk & -Bk
                v = low.bit_length() - 1
                Bk ^= low
                if w[v] <= lhat + EPS or ub + w[v] - lhat <= budget + EPS:
                    Bk &= ~A[v]
                    Brest ^= low
                    I.append(v)
                    if w[v] > lhat:
                        ub += w[v] - lhat
                        lhat = w[v]
            if not I:
                break
            I.sort(key=lambda x: (-w[x], x))
            classes.append([[x, w[x]] for x in I])             # [vertex, load], loads = weights (eq. 13)
        B = sorted(bits(Brest), key=lambda x: (-w[x], x))
        if not B:
            return B
        sets = classes
        extra = [0.0]                                          # implicit singleton loads (weight accounted by the gap)
        locked: set[int] = set()

        def gap() -> float:
            return budget - sum(S[0][1] for S in sets) - extra[0]

        def first_nb(v, I):
            for k, (u, _) in enumerate(I):
                if (A[v] >> u) & 1:
                    return k
            return None

        def cover(v) -> bool:                                  # Algorithm 2 (COVER): one independent set, rules R1-R3
            for I in sets:
                lh, k = I[0][1], first_nb(v, I)
                if k is None:
                    if w[v] <= lh + EPS:                       # R1
                        load = w[v]
                    else:                                      # R2
                        cost = w[v] - lh
                        if cost > gap() + EPS:
                            continue
                        extra[0] += cost
                        load = lh
                    pos = 0
                    while pos < len(I) and I[pos][1] >= load:
                        pos += 1
                    I.insert(pos, [v, load])
                    return True
                lvl = I[k][1]                                  # R3
                beta = lh - lvl
                cost = max(w[v] - beta, 0.0)
                if cost > gap() + EPS:
                    continue
                if k > 0 and beta > EPS:
                    newset = [[u, l - lvl] for (u, l) in I[:k] if l - lvl > EPS]
                    newset.append([v, min(beta, w[v])])
                    newset.sort(key=lambda x: -x[1])
                    for t in range(k):
                        I[t][1] = lvl
                    sets.append(newset)
                extra[0] += cost
                return True
            return False

        def mcover(v) -> bool:                                 # Algorithm 3 (MCOVER): several independent sets
            delta, used, g = 0.0, [], gap()
            for si, I in enumerate(sets):
                if si in locked:
                    continue
                k = first_nb(v, I)
                cap = I[0][1] if k is None else I[0][1] - I[k][1]
                if cap <= EPS:
                    continue
                delta += cap
                used.append(si)
                if delta + g >= w[v] - EPS:
                    extra[0] += max(w[v] - delta, 0.0)
                    locked.update(used)
                    return True
            return False

        for v in list(reversed(B)):                            # lowest weight first (Alg. 4, lines 6-8)
            if cover(v):
                B.remove(v)
        for v in list(reversed(B)):                            # Alg. 4, lines 12-16
            if mcover(v):
                B.remove(v)
        assert budget - sum(S[0][1] for S in sets) - extra[0] >= -1e-6, "cover bound exceeds budget"
        return B

    def search(Vhat: int, C: list[int], wC: float, B: list[int]):  # Algorithm 5 (BBMCW)
        for b in B:
            stats.nodes += 1
            if should_stop is not None and should_stop():
                raise _Stop("cancelled")
            if node_limit is not None and stats.nodes > node_limit:
                raise _Stop("node_limit")
            if time_limit is not None and time.perf_counter() - t0 > time_limit:
                raise _Stop("time_limit")
            stats.branches += 1
            Vb = Vhat & A[b]
            newC, newW = C + [b], wC + w[b]
            if newW > best["w"] + EPS and (accept is None or accept([order[i] for i in newC])):
                best["C"], best["w"] = newC, newW
                stats.incumbent_updates += 1
                if on_incumbent is not None:
                    on_incumbent([order[i] for i in newC], newW)
            budget = best["w"] - newW
            if Vb and restrict is not None:
                kept = restrict(newC, Vb, budget)
                stats.pruned_by_feasibility += Vb.bit_count() - kept.bit_count()
                Vb = kept
            if Vb:
                Bb = gen_branch_set(Vb, budget)
                stats.bound_evaluations += 1
                stats.pruned_by_bound += Vb.bit_count() - len(Bb)
                if hook is not None:
                    hook(Vb, budget, Bb)
                if Bb:
                    search(Vb, newC, newW, Bb)
            Vhat &= ~(1 << b)

    reason = None
    try:
        V = (1 << n) - 1
        if restrict is not None:
            V = restrict([], V, best["w"])
        B0 = gen_branch_set(V, best["w"])
        stats.bound_evaluations += 1
        stats.pruned_by_bound += V.bit_count() - len(B0)
        if hook is not None:
            hook(V, best["w"], B0)
        search(V, [], 0.0, B0)
    except _Stop as s:
        reason = s.reason
    stats.runtime_s = time.perf_counter() - t0
    found = best["C"] is not None
    members = sorted(order[i] for i in best["C"]) if found else []
    return BBMCWResult(members, best["w"] if found else 0.0, reason or "optimal", reason is None, stats, found)
