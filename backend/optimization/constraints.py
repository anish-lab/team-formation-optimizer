"""Team-count / team-size constraints, leftover policies, feasibility checks and assignment validation.

Policies (cfg["policy"]) are *presets* that resolve into explicit low-level constraints:
  leave_unassigned   (A) sizes fixed = preferred_size, leftovers allowed
  variable_sizes     (B) sizes in [min_size, max_size], leftovers allowed unless full_coverage=true
  smaller_final_team (C) sizes <= preferred_size, at most ONE team smaller than preferred (>= min_size)
  strict_equal       (D) all teams exactly preferred_size, leftovers reported
  full_coverage      (E) every candidate must be in exactly one team
Nothing is silently relaxed: if the resolved constraints cannot be met a structured issue list is returned.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict

POLICIES = ("leave_unassigned", "variable_sizes", "smaller_final_team", "strict_equal", "full_coverage")
PRIORITIES = ("coverage_first", "quality_first")


class ConstraintError(Exception):
    def __init__(self, issues: list[dict]):
        self.issues = issues
        super().__init__("; ".join(i["message"] for i in issues))


def issue(code: str, message: str, suggestions=()) -> dict:
    return {"code": code, "message": message, "suggestions": list(suggestions)}


@dataclass
class TeamConstraints:
    min_size: int
    max_size: int
    teams_min: int
    teams_max: int
    full_coverage: bool
    equal_sizes: bool
    preferred_size: int
    max_short_teams: int | None      # None = unrestricted; 1 = policy C
    priority: str                    # lexicographic: coverage_first -> (coverage, quality); quality_first -> quality
    policy: str = "variable_sizes"

    def to_dict(self) -> dict:
        return asdict(self)


def _int(cfg, key, default, minimum=1):
    v = cfg.get(key, None)
    if v is None or v == "":
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or v < minimum:
        raise ConstraintError([issue("invalid_setting", f"'{key}' must be an integer >= {minimum}.")])
    return int(v)


def resolve_constraints(n: int, cfg: dict) -> TeamConstraints:
    policy = cfg.get("policy", "variable_sizes")
    if policy not in POLICIES:
        raise ConstraintError([issue("invalid_setting", f"Unknown policy '{policy}'.", [f"Use one of {POLICIES}"])])
    priority = cfg.get("priority", "coverage_first")
    if priority not in PRIORITIES:
        raise ConstraintError([issue("invalid_setting", f"Unknown priority '{priority}'.", [f"Use one of {PRIORITIES}"])])
    pref = _int(cfg, "preferred_size", 4)
    num = _int(cfg, "num_teams", None)
    strict_count = bool(cfg.get("strict_team_count", True))
    strict_size = bool(cfg.get("strict_team_size", False))
    equal = bool(cfg.get("equal_sizes", False))
    full = bool(cfg.get("full_coverage", False))
    short = None
    if policy in ("leave_unassigned", "strict_equal") or strict_size:
        kmin = kmax = pref
        equal = True
    elif policy == "smaller_final_team":
        kmax = pref
        kmin = _int(cfg, "min_size", min(2, pref))
        short = 1
        full = bool(cfg.get("full_coverage", True))
    else:
        kmin = _int(cfg, "min_size", pref)
        kmax = _int(cfg, "max_size", max(kmin, pref) + 1)
    if policy == "full_coverage":
        full = True
    if kmin > kmax:
        raise ConstraintError([issue("invalid_setting", f"min_size ({kmin}) exceeds max_size ({kmax}).")])
    if num is not None:
        tmax, tmin = num, (num if strict_count else 1)
    elif policy in ("leave_unassigned", "strict_equal"):
        tmin = tmax = n // pref
    elif policy == "smaller_final_team":
        tmin = tmax = math.ceil(n / pref)
    else:
        tmin = math.ceil(n / kmax) if full else 1
        tmax = n // kmin
    return TeamConstraints(kmin, kmax, tmin, tmax, full, equal, pref, short, priority, policy)


def _total_intervals(tc: TeamConstraints, t: int):
    if tc.equal_sizes:
        return [(t * s, t * s) for s in range(tc.min_size, tc.max_size + 1)]
    if tc.max_short_teams is not None:
        return [((t - 1) * tc.max_size + tc.min_size, t * tc.max_size)]
    return [(t * tc.min_size, t * tc.max_size)]


def check_feasibility(n: int, tc: TeamConstraints) -> list[dict]:
    """Arithmetic feasibility (ignores the graph).  Empty list = arithmetically feasible."""
    if tc.teams_max < 1:
        return [issue("no_team_possible",
                      f"The settings allow {tc.teams_max} teams for {n} candidates (e.g. fewer candidates than the team size).",
                      ["Reduce team size / minimum size", "Increase the number of teams", "Provide more candidates"])]
    for t in range(max(tc.teams_min, 1), tc.teams_max + 1):
        for lo, hi in _total_intervals(tc, t):
            if lo <= n and (not tc.full_coverage or n <= hi):
                return []
    sug = []
    msg = (f"No team count between {tc.teams_min} and {tc.teams_max} with sizes {tc.min_size}-{tc.max_size} "
           f"can {'cover all' if tc.full_coverage else 'be filled from'} {n} candidates")
    if tc.teams_min * tc.min_size > n:
        msg += f": {tc.teams_min} teams need at least {tc.teams_min * tc.min_size} candidates."
        sug += ["Reduce the required number of teams", "Reduce the minimum team size", "Provide more candidates"]
    elif tc.full_coverage:
        msg += f": at most {tc.teams_max * tc.max_size} candidates fit."
        sug += ["Increase the maximum team size", "Increase the number of teams",
                "Allow unassigned candidates (turn off full coverage)"]
        if tc.equal_sizes:
            sug.append("Allow variable team sizes")
    else:
        msg += "."
        sug += ["Relax equal-size / smaller-final-team rules", "Change the number of teams"]
    return [issue("infeasible_counts", msg, sug)]


def validate_assignment(graph, tc: TeamConstraints, teams: list[list[int]]) -> list[str]:
    """Return a list of violated hard constraints (empty = valid)."""
    v = []
    seen: set[int] = set()
    for t in teams:
        if not graph.is_clique(t):
            v.append(f"team {sorted(t)} is not a clique")
        if not (tc.min_size <= len(t) <= tc.max_size):
            v.append(f"team size {len(t)} outside [{tc.min_size},{tc.max_size}]")
        if seen & set(t):
            v.append("candidate appears in more than one team")
        seen |= set(t)
    if not (tc.teams_min <= len(teams) <= tc.teams_max):
        v.append(f"team count {len(teams)} outside [{tc.teams_min},{tc.teams_max}]")
    if tc.full_coverage and len(seen) != graph.n:
        v.append("full coverage required but candidates are unassigned")
    if tc.equal_sizes and len({len(t) for t in teams}) > 1:
        v.append("equal team sizes required")
    if tc.max_short_teams is not None and sum(len(t) < tc.preferred_size for t in teams) > tc.max_short_teams:
        v.append("too many teams smaller than the preferred size")
    return v


def assignment_key(graph, tc: TeamConstraints, teams) -> tuple:
    cov = sum(len(t) for t in teams)
    q = sum(graph.score(t) for t in teams)
    return (cov if tc.priority == "coverage_first" else 0, q)
