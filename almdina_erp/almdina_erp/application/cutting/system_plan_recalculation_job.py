from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

IDLE = "idle"
QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"

ENQUEUE = "enqueue"
MARK_PENDING_RERUN = "mark_pending_rerun"
SKIP = "skip"

ACTIVE_STATUSES = frozenset({QUEUED, RUNNING})
TERMINAL_STATUSES = frozenset({COMPLETED, FAILED, IDLE})


def _row_value(row: Any, fieldname: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(fieldname)
    return getattr(row, fieldname, None)


def has_cuttable_pieces(rows: list[Any] | tuple[Any, ...] | None) -> bool:
    """True when at least one persisted piece can enter the optimizer."""

    for row in rows or ():
        try:
            qty = float(_row_value(row, "qty") or 0)
            width = float(_row_value(row, "width_cm") or 0)
            length = float(_row_value(row, "length_cm") or 0)
        except (TypeError, ValueError):
            continue
        if qty > 0 and width > 0 and length > 0:
            return True
    return False


def system_draft_is_stale(
    *,
    has_system_draft: bool,
    needs_recalculation: bool,
    stored_fingerprint: str | None,
    expected_fingerprint: str | None,
) -> bool:
    """Decide whether an existing System draft no longer matches order inputs."""

    if not has_system_draft:
        return False
    if needs_recalculation:
        return True
    stored = str(stored_fingerprint or "").strip()
    expected = str(expected_fingerprint or "").strip()
    if stored and stored == expected:
        return False
    return True


@dataclass(frozen=True, slots=True)
class RecalculationFacts:
    has_recalculate_capability: bool
    lifecycle_allows: bool
    has_cuttable_pieces: bool
    has_system_draft: bool
    system_draft_is_stale: bool


@dataclass(frozen=True, slots=True)
class JobState:
    order_name: str
    status: str
    generation: int
    pending_rerun: bool = False
    queued_at: str = ""
    error: str = ""

    def as_cache_value(self) -> dict[str, Any]:
        return {
            "order_name": self.order_name,
            "status": self.status,
            "generation": int(self.generation or 0),
            "pending_rerun": bool(self.pending_rerun),
            "queued_at": str(self.queued_at or ""),
            "error": str(self.error or ""),
        }

    @classmethod
    def from_cache_value(cls, value: Mapping[str, Any] | None) -> JobState | None:
        if not value:
            return None
        order_name = str(value.get("order_name") or "").strip()
        status = str(value.get("status") or IDLE).strip() or IDLE
        if not order_name:
            return None
        return cls(
            order_name=order_name,
            status=status,
            generation=int(value.get("generation") or 0),
            pending_rerun=bool(value.get("pending_rerun")),
            queued_at=str(value.get("queued_at") or ""),
            error=str(value.get("error") or ""),
        )


@dataclass(frozen=True, slots=True)
class EnqueueDecision:
    action: str
    reason: str
    next_generation: int = 0


def decide_enqueue_system_plan_recalculation(
    facts: RecalculationFacts,
    current: JobState | None = None,
) -> EnqueueDecision:
    """Decide whether Save should start, coalesce, or skip a background recalc."""

    if not facts.has_recalculate_capability:
        return EnqueueDecision(SKIP, "no_capability")
    if not facts.lifecycle_allows:
        return EnqueueDecision(SKIP, "lifecycle_blocked")
    if not facts.has_cuttable_pieces:
        return EnqueueDecision(SKIP, "no_pieces")

    needs_work = (not facts.has_system_draft) or facts.system_draft_is_stale
    if not needs_work:
        return EnqueueDecision(SKIP, "fresh")

    generation = int(current.generation or 0) if current else 0
    current_status = str(current.status or IDLE) if current else IDLE
    if current_status in ACTIVE_STATUSES:
        return EnqueueDecision(MARK_PENDING_RERUN, "already_active", generation)
    return EnqueueDecision(
        ENQUEUE,
        "stale" if facts.has_system_draft else "missing_system_draft",
        generation + 1,
    )


def decide_after_system_plan_recalculation_job(
    *,
    succeeded: bool,
    pending_rerun: bool,
    still_stale: bool,
) -> str:
    """Choose the next job status after one optimizer run finishes."""

    if pending_rerun and still_stale:
        return ENQUEUE
    if succeeded:
        return COMPLETED
    return FAILED


def job_presentation(state: JobState | None) -> dict[str, Any]:
    """Safe workspace overlay: progress only, never cost scalars."""

    if state is None:
        return {
            "status": IDLE,
            "generation": 0,
            "pending_rerun": False,
            "error": "",
        }
    error = str(state.error or "") if state.status == FAILED else ""
    return {
        "status": state.status,
        "generation": int(state.generation or 0),
        "pending_rerun": bool(state.pending_rerun),
        "error": error,
    }


__all__ = [
    "ACTIVE_STATUSES",
    "COMPLETED",
    "ENQUEUE",
    "FAILED",
    "IDLE",
    "MARK_PENDING_RERUN",
    "QUEUED",
    "RUNNING",
    "SKIP",
    "TERMINAL_STATUSES",
    "EnqueueDecision",
    "JobState",
    "RecalculationFacts",
    "decide_after_system_plan_recalculation_job",
    "decide_enqueue_system_plan_recalculation",
    "has_cuttable_pieces",
    "job_presentation",
    "system_draft_is_stale",
]
