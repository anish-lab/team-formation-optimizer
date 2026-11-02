import random
from optimization.models import Graph


def rand_graph(seed, n, p=0.6, edge_weights=True, zero_weights=False):
    rng = random.Random(seed)
    edges, ew = [], {}
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < p:
                edges.append((i, j))
                ew[(i, j)] = round(rng.random(), 3) if edge_weights else 0.0
    vw = [0.0 if zero_weights else round(rng.random(), 3) for _ in range(n)]
    return Graph.from_edges(n, edges, vw, ew)
