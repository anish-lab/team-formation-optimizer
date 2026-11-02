"""In-memory task registry (one isolated Task per optimisation; no global dataset state)."""
from __future__ import annotations
import threading
import time
import uuid
import logging
from optimization.team_conflict_solver import solve_teams_bbmcw
from optimization.greedy_baseline import greedy_teams
from evaluation.reports import build_result

log = logging.getLogger("tasks")


class Task:
    def __init__(self, built, tc, limits, config):
        self.id = uuid.uuid4().hex[:12]
        self.built, self.tc, self.limits, self.config = built, tc, limits, config
        self.status = "queued"
        self.created = time.time()
        self.started = None
        self.finished = None
        self.progress: dict = {}
        self.result = None
        self.error = None
        self.cancel = threading.Event()

    def public(self) -> dict:
        end = self.finished or time.time()
        return {"task_id": self.id, "status": self.status, "elapsed_s": (end - self.started) if self.started else 0.0,
                "progress": dict(self.progress), "error": self.error, "has_result": self.result is not None}

    def run(self):
        self.status, self.started = "running", time.time()
        try:
            L = self.limits
            res = solve_teams_bbmcw(self.built.graph, self.tc, L["time_limit"], L["node_limit"], L["max_cliques"],
                                    self.cancel.is_set, self.progress)
            heuristic, viol = False, None
            if res.status == "too_large" and L["allow_heuristic"]:
                res, viol = greedy_teams(self.built.graph, self.tc)
                res.issues = [{"code": "heuristic_fallback", "message": "Exact search was too large; a labelled greedy heuristic was used.", "suggestions": []}]
                heuristic = True
            self.result = build_result(self.built, self.tc, res, heuristic, viol)
            self.status = "cancelled" if res.termination_reason == "cancelled" else "finished"
        except Exception:  # never leak stack traces to clients
            log.exception("optimisation task %s failed", self.id)
            self.status, self.error = "failed", {"code": "solver_error", "message": "The optimisation failed unexpectedly."}
        finally:
            self.finished = time.time()


class TaskStore:
    def __init__(self, max_tasks=50):
        self.tasks: dict[str, Task] = {}
        self.max = max_tasks
        self.lock = threading.Lock()

    def add(self, task: Task) -> None:
        with self.lock:
            while len(self.tasks) >= self.max:
                old = min((t for t in self.tasks.values() if t.status not in ("queued", "running")),
                          key=lambda t: t.created, default=None)
                if old is None:
                    break
                del self.tasks[old.id]
            self.tasks[task.id] = task

    def get(self, tid: str):
        return self.tasks.get(tid)
