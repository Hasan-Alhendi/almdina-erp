from __future__ import annotations

from datetime import datetime, timedelta


# Queue hand-off should complete quickly; long backups may run for hours.
QUEUED_STALE_AFTER = timedelta(minutes=30)
RUNNING_STALE_AFTER = timedelta(hours=8)
PREPARED_STALE_AFTER = timedelta(hours=8)
# Detached restore_runner may outlive ordinary Prepared backups; keep the
# request file alive and only reclaim orphaned restore prep after a full day.
RESTORE_PREPARED_STALE_AFTER = timedelta(hours=24)

# Terminal Failed never blocks a future schedule slot once its key is released.
ACTIVE_SCHEDULE_STATUSES = frozenset({"Queued", "Running", "Prepared", "Completed"})
RECLAIMABLE_STATUSES = frozenset({"Queued", "Running", "Prepared"})
ACTIVE_RESTORE_STATUSES = frozenset({"Queued", "Running", "Prepared"})


def is_schedule_blocking_status(status: object) -> bool:
    return str(status or "").strip() in ACTIVE_SCHEDULE_STATUSES


def is_stale_backup_operation(
    *,
    status: object,
    requested_on: datetime | None,
    started_on: datetime | None,
    now: datetime,
    prepared_limit: timedelta | None = None,
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
    if normalized == "Prepared":
        limit = prepared_limit if prepared_limit is not None else PREPARED_STALE_AFTER
    else:
        limit = RUNNING_STALE_AFTER
    return now - anchor >= limit


__all__ = [
    "ACTIVE_RESTORE_STATUSES",
    "ACTIVE_SCHEDULE_STATUSES",
    "PREPARED_STALE_AFTER",
    "QUEUED_STALE_AFTER",
    "RECLAIMABLE_STATUSES",
    "RESTORE_PREPARED_STALE_AFTER",
    "RUNNING_STALE_AFTER",
    "is_schedule_blocking_status",
    "is_stale_backup_operation",
]
