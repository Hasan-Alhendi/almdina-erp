from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath


FREQUENCIES = frozenset({"Daily", "Weekly", "Monthly"})
WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


@dataclass(frozen=True, slots=True)
class BackupSchedule:
    frequency: str
    time: str
    weekday: str = "Monday"
    day_of_month: int = 1

    def validated(self) -> "BackupSchedule":
        frequency = str(self.frequency or "").strip().title()
        if frequency not in FREQUENCIES:
            raise ValueError("Backup frequency must be Daily, Weekly, or Monthly.")

        match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?", str(self.time or "").strip())
        if not match:
            raise ValueError("Backup time must use HH:MM format.")

        weekday = str(self.weekday or "").strip().title()
        if frequency == "Weekly" and weekday not in WEEKDAYS:
            raise ValueError("Backup weekday is invalid.")

        try:
            day_of_month = int(self.day_of_month)
        except (TypeError, ValueError) as exc:
            raise ValueError("Backup day of month must be between 1 and 31.") from exc
        if not 1 <= day_of_month <= 31:
            raise ValueError("Backup day of month must be between 1 and 31.")

        return BackupSchedule(
            frequency=frequency,
            time=f"{match.group(1)}:{match.group(2)}",
            weekday=weekday or "Monday",
            day_of_month=day_of_month,
        )


def due_schedule_key(target: str, schedule: BackupSchedule, now: datetime) -> str | None:
    """Return a stable key only during the configured schedule minute.

    Monthly days are clamped to the final day of shorter months so a schedule
    configured for day 31 still runs every month.
    """

    resolved = schedule.validated()
    hour, minute = (int(value) for value in resolved.time.split(":"))
    if (now.hour, now.minute) != (hour, minute):
        return None

    prefix = str(target or "").strip().lower()
    if not prefix:
        raise ValueError("Backup schedule target is required.")

    if resolved.frequency == "Daily":
        return f"{prefix}:daily:{now:%Y-%m-%d}"
    if resolved.frequency == "Weekly":
        if now.weekday() != WEEKDAYS.index(resolved.weekday):
            return None
        iso_year, iso_week, _ = now.isocalendar()
        return f"{prefix}:weekly:{iso_year}-W{iso_week:02d}"

    final_day = calendar.monthrange(now.year, now.month)[1]
    if now.day != min(resolved.day_of_month, final_day):
        return None
    return f"{prefix}:monthly:{now:%Y-%m}"


def normalize_remote_path(value: object) -> str:
    """Validate an absolute, non-root POSIX directory without traversal."""

    raw = str(value or "").strip()
    if not raw or "\x00" in raw or not raw.startswith("/"):
        raise ValueError("Remote backup path must be an absolute POSIX path.")
    segments = raw.split("/")
    if any(segment in {".", ".."} for segment in segments):
        raise ValueError("Remote backup path cannot contain traversal segments.")
    normalized = str(PurePosixPath(raw))
    if normalized == "/":
        raise ValueError("Remote backup path cannot be the server root.")
    return normalized


def backup_group_identifier(filename: object, site_slug: object) -> str | None:
    """Identify only complete-site artifacts emitted by Frappe v16."""

    name = str(filename or "")
    slug = str(site_slug or "").strip()
    if not slug or "/" in name or "\\" in name:
        return None
    prefix = rf"(?P<identifier>\d{{8}}_\d{{6}}-{re.escape(slug)})-"
    suffix = (
        r"(?:site_config_backup(?:-enc)?\.json|"
        r"database(?:-enc)?\.sql\.gz|"
        r"files(?:-enc)?\.(?:tar|tgz)|"
        r"private-files(?:-enc)?\.(?:tar|tgz))"
    )
    match = re.fullmatch(prefix + suffix, name)
    return match.group("identifier") if match else None


def retention_candidates(identifiers: list[str] | tuple[str, ...], keep_last: int) -> tuple[str, ...]:
    try:
        limit = int(keep_last)
    except (TypeError, ValueError) as exc:
        raise ValueError("Backup retention must be a positive integer.") from exc
    if limit < 1:
        raise ValueError("Backup retention must be a positive integer.")
    ordered = sorted({str(value) for value in identifiers if value}, reverse=True)
    return tuple(ordered[limit:])


__all__ = [
    "BackupSchedule",
    "FREQUENCIES",
    "WEEKDAYS",
    "backup_group_identifier",
    "due_schedule_key",
    "normalize_remote_path",
    "retention_candidates",
]
