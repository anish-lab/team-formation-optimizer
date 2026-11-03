"""AMTS (Adaptive Multistart Tabu Search): the initial solution heuristic named by the paper (Section 2.5, p. 17).

The paper cites Wu & Hao, J. Comb. Optim. 26(1), 2013 and gives no details of its own; this follows Wu & Hao's Section 2.  AMTS looks
for a clique of a fixed size k: S is a set of k vertices, f(S) counts the edges inside S, and S is a clique when f(S) = k(k-1)/2.
  * Constrained swap: swap a non-tabu u in S of minimum degree-into-S with a non-tabu v outside S of maximum degree-into-S.
  * Tabu tenure: Tu = l + Random(C), Tv = 0.6*l + Random(0.6*C), with l = min(missing edges, 10) and C = max(k/40, 6).
  * Probabilistic move: at a local optimum, with probability min((missing+2)/|V|, 0.1), swap a random u with a low-degree v.
  * Restart: after L = |V|*k iterations without improvement, rebuild S greedily, using the frequency memory to break ties.
Adaptation, since Wu & Hao's AMTS ignores weights and the paper does not say how it applied AMTS to the weighted problem:
the search continues after a clique is found, the heaviest clique over the clique sizes is kept, and weight breaks ties among moves.
The iteration limit is also far below Wu & Hao's 10^8, because this only supplies a starting solution.
"""
from __future__ import annotations
import time
import numpy as np

DEFAULT_SEED = 0
CLIQUES_PER_SIZE = 20


def _row(a: int, n: int, nbytes: int) -> np.ndarray:
    packed = np.frombuffer(a.to_bytes(nbytes, "little"), dtype=np.uint8)
    return np.unpackbits(packed, bitorder="little")[:n].astype(bool)


def clique_size_limit(adj: list[int]) -> int:
    """A greedy colouring's colour count: no clique can be larger, so larger sizes need not be searched."""
    left, colours = (1 << len(adj)) - 1, 0
    while left:
        colours += 1
        cand = left
        while cand:
            low = cand & -cand
            v = low.bit_length() - 1
            left ^= low
            cand &= ~adj[v] & ~low
    return colours


def amts(weights: list[float], adj: list[int], sizes, accept=None, iterations: int | None = None, deadline: float | None = None,
         should_stop=None, seed: int = DEFAULT_SEED) -> tuple[list[int] | None, float]:
    """Heaviest clique found across the clique sizes in `sizes` (ascending).  With `accept`, only accepted cliques count."""
    n = len(weights)
    best, best_w = None, -1.0
    if n == 0:
        return best, best_w
    nbytes = (n + 7) // 8
    w = np.asarray(weights, dtype=float)
    rng = np.random.default_rng(seed)
    cache: dict[int, np.ndarray] = {}
    limit = iterations if iterations is not None else min(50 * n + 200, 5000)
    density = sum(a.bit_count() for a in adj) / max(n * (n - 1), 1)

    def row(v: int) -> np.ndarray:
        r = cache.get(v)
        if r is None:
            r = cache[v] = _row(adj[v], n, nbytes)
        return r

    def out_of_time() -> bool:
        return (deadline is not None and time.perf_counter() > deadline) or (should_stop is not None and should_stop())

    def record(members: list[int]):
        nonlocal best, best_w
        if accept is None:                                     # the paper's heuristic solution is a maximal clique (p. 4)
            cand = (1 << n) - 1
            for v in members:
                cand &= adj[v]
            while cand:
                v = max((i for i in np.flatnonzero(_row(cand, n, nbytes))), key=lambda i: (w[i], -i))
                members = members + [int(v)]
                cand &= adj[int(v)]
        elif not accept(members):
            return
        total = float(w[members].sum())
        if total > best_w + 1e-9:
            best, best_w = list(members), total

    def construct(k: int, freq: np.ndarray) -> np.ndarray:
        """Restart: first a least-moved vertex, then most edges into S (ties: least moved, then heavier, then random)."""
        S = np.zeros(n, dtype=bool)
        d = np.zeros(n, dtype=np.int32)
        for _ in range(k):
            out = np.flatnonzero(~S)
            top = out[d[out] == d[out].max()]
            least = top[freq[top] == freq[top].min()]
            heavy = least[w[least] == w[least].max()]
            v = int(rng.choice(heavy))
            S[v] = True
            d += row(v)
        return S

    for k in sizes:
        if k < 1 or k > n or out_of_time():
            break
        target = k * (k - 1) // 2
        freq = np.zeros(n, dtype=np.int64)
        found_at_k = 0
        spent = 0
        depth = n * k
        C = max(k // 40, 6)
        while spent < limit and found_at_k < CLIQUES_PER_SIZE and not out_of_time():
            spent += 1
            S = construct(k, freq)
            members = np.flatnonzero(S)
            d = np.zeros(n, dtype=np.int32)
            for v in members:
                d += row(int(v))
            f = int(d[members].sum()) // 2
            tabu = np.zeros(n, dtype=np.int64)
            best_f, stale, it = f, 0, 0
            while spent < limit and stale < depth:
                if f == target:
                    record([int(v) for v in np.flatnonzero(S)])
                    found_at_k += 1
                    freq[S] += 1                               # steer the next restart towards different vertices
                    break
                spent += 1
                it += 1
                if (it & 255) == 0 and out_of_time():
                    break
                free = tabu <= it
                ins, outs = np.flatnonzero(S & free), np.flatnonzero(~S & free)
                if ins.size == 0 or outs.size == 0:
                    tabu[:] = 0
                    continue
                A = ins[d[ins] == d[ins].min()]
                B = outs[d[outs] == d[outs].max()]
                u = v = -1
                for a in A[np.argsort(w[A], kind="stable")][:16]:      # prefer a non-adjacent pair, which gains one edge more
                    cand = B[~row(int(a))[B]]
                    if cand.size:
                        u, v = int(a), int(cand[np.argmax(w[cand])])
                        break
                missing = target - f
                gain = int(d[B[0]]) - int(d[A[0]]) - (0 if u >= 0 else 1)
                if gain <= 0 and rng.random() < min((missing + 2) / n, 0.1):       # probabilistic move at a local optimum
                    low = np.flatnonzero(~S & (d < int(k * density)))
                    if low.size:
                        u, v = int(rng.choice(np.flatnonzero(S))), int(rng.choice(low))
                if u < 0:
                    u, v = int(rng.choice(A)), int(B[np.argmax(w[B])])
                f += int(d[v]) - int(d[u]) - int(row(u)[v])
                S[u], S[v] = False, True
                d += row(v).astype(np.int32) - row(u).astype(np.int32)
                freq[u] += 1
                freq[v] += 1
                l1 = min(target - f, 10)
                tabu[u] = it + l1 + int(rng.integers(0, C))
                tabu[v] = it + int(0.6 * l1) + int(rng.integers(0, max(int(0.6 * C), 1)))
                if f > best_f:
                    best_f, stale = f, 0
                else:
                    stale += 1
            if (freq > k).all():                               # frequency memory reset
                freq[:] = 0
        if found_at_k == 0 and accept is None:
            break                                              # a clique of size k was not found, so stop growing k
    return best, best_w
