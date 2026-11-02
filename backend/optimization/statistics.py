"""Search statistics shared by all solvers."""
from __future__ import annotations
from dataclasses import dataclass, asdict, fields


@dataclass
class SearchStats:
    nodes: int = 0
    branches: int = 0                 # branches considered (expanded or pruned)
    pruned_by_bound: int = 0
    pruned_by_feasibility: int = 0
    incumbent_updates: int = 0
    bound_evaluations: int = 0
    complete_teams_examined: int = 0
    runtime_s: float = 0.0

    def merge(self, other: "SearchStats") -> None:
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pruning_efficiency"] = self.pruned_by_bound / self.branches if self.branches else 0.0
        return d
