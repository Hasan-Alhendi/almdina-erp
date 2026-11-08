from __future__ import annotations

from datetime import datetime, timedelta


# Queue hand-off should complete quickly; long backups may run for hours.
QUEUED_STALE_AFTER = timedelta(minutes=30)
RUNNING_STALE_AFTER = timedelta(hours=8)
PREPARED_STALE_AFTER = timedelta(hours=8)

# Terminal Failed never blocks a future schedule slot once its key is released.
ACTIVE_SCHEDULE_STATUSES = frozenset({"Queued", "Running", "Prepared", "Completed"})
RECLAIMABLE_STATUSES = frozenset({"Queued", "Running", "Prepared"})


def is_schedule_blocking_status(status: object) -> bool:
    return str(status or "").strip() in ACTIVE_SCHEDULE_STATUSES


def is_stale_backup_operation(
    *,
    status: object,
    requested_on: datetime | None,
    started_on: datetime | None,
    now: datetime,
) -> bool:
    """Return True when a non-terminal operation has exceeded its age budget."""

    normalized = str(status or "").strip()
    if normalized not in RECLAIMABLE_STATUSES:
        return False
    if normalized == "Queued":
        if requested_on is None:
            return True
        return now - requested_on >= QUEUED_STALE_AFTER
    anchor = started_on or requested_on
    if anchor is None:
        return True
    limit = PREPARED_STALE_AFTER if normalized == "Prepared" else RUNNING_STALE_AFTER
    return now - anchor >= limit


__all__ = [
    "ACTIVE_SCHEDULE_STATUSES",
    "PREPARED_STALE_AFTER",
    "QUEUED_STALE_AFTER",
    "RECLAIMABLE_STATUSES",
    "RUNNING_STALE_AFTER",
    "is_schedule_blocking_status",
    "is_stale_backup_operation",
]
