"""Opt-in ABC research, bounded independently of native winner selection."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from collections import deque
import math
import time

from .cut_line_quality import final_cut_quality_key, plan_cut_line_quality
from .evaluation import placement_permission_errors, validate_plan
from .plan_portfolio import geometry_signature, manufacturing_export_rejection
from .regular_templates import regular_template_candidates, supports_regular_proposals


@dataclass(frozen=True)
class ABCSearchPolicy:
    schedule: bool = False
    retention: bool = False
    templates: bool = False
    share: float = .10

    def __post_init__(self):
        if not math.isfinite(self.share) or not 0 < self.share <= .20:
            raise ValueError("ABC research share must be in (0, .20]")

    @property
    def enabled(self):
        return self.schedule or self.retention or self.templates


@dataclass
class LocalPackingBudget:
    limit: int = 24
    counts: dict = field(default_factory=lambda: dict(regroup=0, templates=0))

    def take(self, stage):
        if sum(self.counts.values()) >= self.limit:
            return False
        if stage == "templates" and self.counts[stage] >= 6:
            return False
        self.counts[stage] += 1
        return True


class ABCSearchSession:
    """One call owns every proposal, metric cap and detached side-pool entry."""
    def __init__(self, policy, sources, width, height, kerf, machine, mirror, metrics, deadline):
        self.policy, self.sources = policy, sources
        self.width, self.height, self.kerf = width, height, kerf
        self.machine, self.mirror, self.metrics = machine, mirror, metrics
        self.deadline = deadline
        self.budget = LocalPackingBudget()
        self.pool = []
        self.best_boards = math.inf
        self.profiles = 0
        self.trace = dict(generated=0, validated=0, rejected=0, nominated=0, followup_regroups=0,
                          side_pool_peak=0, reason="pending")

    def observe_valid(self, plan):
        """Caller has already applied the independent full manufacturing gates."""
        boards = len(plan.get("sheets") or [])
        if boards < self.best_boards:
            self.best_boards = boards
            self.pool = [p for p in self.pool if len(p[1]["sheets"]) <= boards]
        if (not self.policy.retention or boards > self.best_boards or self.profiles >= 12
                or not supports_regular_proposals(plan, self.sources)
                or time.monotonic() >= self.deadline):
            return
        signature = geometry_signature(plan)
        if any(geometry_signature(p[1]) == signature for p in self.pool):
            return
        self.profiles += 1
        profile = plan_cut_line_quality(plan, self.kerf)
        if profile is None:
            return
        key = (tuple(plan["industrial_rank"][:4]), final_cut_quality_key(profile),
               tuple(plan["industrial_rank"][4:]))
        self.pool.append((key, deepcopy(plan)))
        self.pool.sort(key=lambda item: item[0])
        self.pool = self.pool[:3]
        self.trace["side_pool_peak"] = max(self.trace["side_pool_peak"], len(self.pool))

    def consider(self, raw, *, deadline):
        from .optimizer import enrich_plan_metrics
        self.trace["generated"] += 1
        if (raw.get("unplaced") or len(raw.get("sheets") or []) > self.best_boards
                or manufacturing_export_rejection(raw)
                or validate_plan(raw, self.sources, self.width, self.height,
                                 kerf_cm=self.kerf, deadline_monotonic=deadline)
                or placement_permission_errors(raw, self.sources, mirroring_allowed=self.mirror)):
            self.trace["rejected"] += 1
            return None
        candidate = enrich_plan_metrics(raw, str(raw.get("method_key") or ""),
                                        self.machine, **self.metrics)
        self.trace["validated"] += 1
        self.observe_valid(candidate)
        return candidate

    def run(self, initial, offer, seconds):
        from .plan_search import _regrouped_board_candidates
        if not (self.policy.schedule or self.policy.templates):
            self.trace["reason"] = "retention_only"
            return
        if (self.machine not in {"Auto", "CNC Router"}
                or not supports_regular_proposals(initial, self.sources)):
            self.trace["reason"] = "unsupported"
            return
        if not math.isfinite(self.best_boards):
            self.trace["reason"] = "no_valid_baseline"
            return
        end = min(self.deadline, time.monotonic()+max(0., seconds)*self.policy.share)
        if time.monotonic() >= end:
            self.trace["reason"] = "deadline"
            return
        self.trace["reason"] = "started"
        regroup = (_regrouped_board_candidates(initial, self.sources, self.width,
            self.height, self.kerf, end, attempt_budget=self.budget,
            yield_attempts=True) if self.policy.schedule else iter(()))
        templates = (regular_template_candidates(initial, self.sources, self.width,
            self.height, self.kerf, budget=self.budget, deadline=end) if self.policy.templates else iter(()))
        # Failed attempts also yield control: a barren A neighborhood cannot
        # consume C's entire window before its first turn (or vice versa).
        jobs = deque([(regroup, False), (templates, True)])
        while jobs and time.monotonic() < end:
            iterator, is_template = jobs.popleft()
            try:
                raw = next(iterator)
            except StopIteration:
                continue
            jobs.append((iterator, is_template))
            if raw is not None:
                candidate = self.consider(raw, deadline=end)
                if candidate is not None:
                    offer(candidate)
                    if (is_template and self.policy.schedule
                            and not self.trace["followup_regroups"]):
                        jobs.append((_regrouped_board_candidates(candidate, self.sources,
                            self.width, self.height, self.kerf, end,
                            attempt_budget=self.budget, yield_attempts=True), False))
                        self.trace["followup_regroups"] = 1

    def nominee(self, native):
        native_signatures = {geometry_signature(p) for p in native}
        for _, plan in self.pool:
            if (len(plan["sheets"]) <= self.best_boards
                    and geometry_signature(plan) not in native_signatures):
                self.trace["nominated"] = 1
                return deepcopy(plan)
        return None
