"""BBMCW: the exact solver for the Maximum Weighted Clique Problem from
  P. San Segundo, F. Furini, J. Artieda, "A new branch-and-bound algorithm for the Maximum Weighted Clique
  Problem", Computers & Operations Research 110 (2019) 18-33.  Page numbers below refer to the 36-page preprint.

Paper parts implemented here: Branching and Pruned Sets (eq. 1, p. 5), Covering Bound with loads (eq. 9-13, p. 7), rules R1-R3
(pp. 8-9), COLOR (Alg. 1, p. 11), COVER (Alg. 2, p. 14), MCOVER (Alg. 3, p. 15), GenBranchSet (Alg. 4, p. 16), the search
(Alg. 5, p. 18), the degeneracy and colour-sort orderings with the choice at the root (pp. 16-17), the limit of 3 vertices per
colour class (p. 17), and AMTS as the initial solution (p. 17, see amts.py).

Choices where the paper's text is silent or inconsistent:
  * Alg. 3 steps 9 and 17 print g - max{Delta - w(v), 0}, but the example in Section 3 charges w(v) - Delta to the gap; so does this code.
  * Alg. 5 step 4 prints w(C) before b is added, but the example in Section 3 uses w(C + b); so does this code, which validity requires.
  * The 3-vertex limit: the paper says COVER and MCOVER are easily tailored but not how.  Here the dropped vertices are kept as one
    placeholder holding their largest load and treated as a neighbour of every vertex, which keeps the bound valid.
  * MCOVER skips sets with no spare capacity instead of removing them, and the gap is recomputed from bound (12) instead of being updated.
  * Colour sort: colours are computed in degeneracy order, following the paper's one-sentence description; [30] may differ in detail.

Team rules are not in the paper and are enforced only through `accept` and `restrict`, which do not change the bound (off by default):
  accept(clique): only accepted cliques may become the incumbent.  Safe, because pruning only discards cliques that cannot beat it.
  restrict(clique, V, budget): may remove from V vertices that cannot lead to an accepted, improving clique.
`use_cover`, `use_mcover` and `use_amts` switch off parts of the algorithm, for the comparison in the paper's Section 4.5 (p. 27).
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from .amts import amts, clique_size_limit
from .statistics import SearchStats

EPS = 1e-9
MAX_SET_SIZE = 3
DROPPED = -1                                                   # placeholder for the vertices dropped by the 3-vertex limit


def bits(mask: int):
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


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
    """First Order (p. 16).  order[new_index] = old_index.  Min-degree vertex goes LAST (ties: smaller weight), repeatedly."""
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


def colour_sort_order(adj, sequence) -> list[int]:
    """Second Order (p. 17).  Greedy independent-set colouring taken in `sequence`, then sort by non-decreasing colour number."""
    left, order = (1 << len(sequence)) - 1, []
    if sequence == list(range(len(sequence))):
        masks = adj
    else:
        masks = relabel(adj, sequence)
    while left:
        cand = left
        while cand:
            low = cand & -cand
            i = low.bit_length() - 1
            order.append(sequence[i])
            left ^= low
            cand &= ~masks[i] & ~low
    return order


def relabel(adj, order) -> list[int]:
    inv = {old: new for new, old in enumerate(order)}
    return [sum(1 << inv[j] for j in bits(adj[old])) for old in order]


def gen_branch_set(V: int, budget: float, w, A, use_cover: bool = True, use_mcover: bool = True, max_set_size: int | None = MAX_SET_SIZE) -> list[int]:
    """Algorithm 4 (GenBranchSet): returns Branching Set B (sorted by non-increasing weight)."""
    if budget < 0:
        return sorted(bits(V), key=lambda x: (-w[x], x))
    # ---- COLOR (Algorithm 1): partial greedy colouring with gap budget ----
    Brest, ub, sets = V, 0.0, []
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
        stored = [[x, w[x]] for x in (I if max_set_size is None else I[:max_set_size])]    # [vertex, load], loads = weights (eq. 13)
        if len(stored) < len(I):
            stored.append([DROPPED, w[I[len(stored)]]])        # Section 2.6: keep only the heaviest vertices
        sets.append(stored)
    B = sorted(bits(Brest), key=lambda x: (-w[x], x))
    if not B:
        return B
    extra = [0.0]                                              # weight charged to the gap, not stored in a set (p. 12)
    locked: set[int] = set()

    def gap() -> float:
        return budget - sum(S[0][1] for S in sets) - extra[0]

    def first_nb(v, I):
        for k, (u, _) in enumerate(I):
            if u == DROPPED or (A[v] >> u) & 1:
                return k
        return None

    def cover(v) -> bool:                                      # Algorithm 2 (COVER): one independent set, rules R1-R3
        for I in sets:
            lh, k = I[0][1], first_nb(v, I)
            if k is None:
                if w[v] <= lh + EPS:                           # R1
                    load = w[v]
                else:                                          # R2
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
            lvl = I[k][1]                                      # R3
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

    def mcover(v) -> bool:                                     # Algorithm 3 (MCOVER): several independent sets
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

    if use_cover:
        for v in list(reversed(B)):                            # lowest weight first (Alg. 4, steps 6-8)
            if cover(v):
                B.remove(v)
    if use_mcover:
        for v in list(reversed(B)):                            # Alg. 4, steps 12-16
            if mcover(v):
                B.remove(v)
    assert budget - sum(S[0][1] for S in sets) - extra[0] >= -1e-6, "cover bound exceeds budget"
    return B


def solve_bbmcw(weights: list[float], adj: list[int], time_limit: float | None = None, node_limit: int | None = None,
                should_stop=None, hook=None, accept=None, restrict=None, initial: list[int] | None = None,
                preordered: bool = False, validate: bool = True, on_incumbent=None, stats: SearchStats | None = None,
                use_cover: bool = True, use_mcover: bool = True, use_amts: bool = True,
                max_set_size: int | None = MAX_SET_SIZE) -> BBMCWResult:
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
    # ---- initial solution (p. 17) ----
    if initial is not None:
        inc = list(initial)
    elif use_amts and accept is None:
        inc, _ = amts(weights, adj, range(1, clique_size_limit(adj) + 1), should_stop=should_stop,
                      deadline=None if time_limit is None else t0 + time_limit)
    else:
        inc = None
    lb = sum(weights[v] for v in inc) if inc is not None else (-1.0 if accept is not None else 0.0)
    # ---- initial ordering: the one with the smaller root Branching Set (p. 17) ----
    if preordered:
        order, w, A = list(range(n)), [float(x) for x in weights], adj
    else:
        options = []
        first = degeneracy_order(weights, adj)
        for candidate in (first, colour_sort_order(adj, first)):
            cw, cA = [float(weights[v]) for v in candidate], relabel(adj, candidate)
            size = len(gen_branch_set((1 << n) - 1, lb, cw, cA, use_cover, use_mcover, max_set_size))
            options.append((size, candidate, cw, cA))
        _, order, w, A = min(options, key=lambda o: o[0])
    inv = {old: new for new, old in enumerate(order)}
    if inc is None:
        best = {"C": None if accept is not None else [], "w": lb}
    else:
        best = {"C": [inv[v] for v in inc], "w": lb}

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
                Bb = gen_branch_set(Vb, budget, w, A, use_cover, use_mcover, max_set_size)
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
        B0 = gen_branch_set(V, best["w"], w, A, use_cover, use_mcover, max_set_size)
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
