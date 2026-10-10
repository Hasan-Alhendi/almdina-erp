from __future__ import annotations

from datetime import datetime

import pytest

from almdina_erp.almdina_erp.domain.backups.policy import (
    BackupSchedule,
    backup_group_identifier,
    due_schedule_key,
    normalize_remote_path,
    retention_candidates,
)


def test_daily_weekly_and_monthly_schedule_keys_are_independent() -> None:
    assert due_schedule_key(
        "local",
        BackupSchedule("Daily", "02:00"),
        datetime(2026, 10, 8, 2, 0),
    ) == "local:daily:2026-10-08"
    assert due_schedule_key(
        "external",
        BackupSchedule("Weekly", "03:15", weekday="Thursday"),
        datetime(2026, 10, 8, 3, 15),
    ) == "external:weekly:2026-W41"
    assert due_schedule_key(
        "local",
        BackupSchedule("Monthly", "01:30", day_of_month=31),
        datetime(2026, 2, 28, 1, 30),
    ) == "local:monthly:2026-02"


def test_schedule_is_not_due_outside_exact_minute_or_selected_day() -> None:
    assert due_schedule_key(
        "local",
        BackupSchedule("Daily", "02:00"),
        datetime(2026, 10, 8, 2, 1),
    ) is None
    assert due_schedule_key(
        "external",
        BackupSchedule("Weekly", "03:15", weekday="Friday"),
        datetime(2026, 10, 8, 3, 15),
    ) is None


@pytest.mark.parametrize("value", ["", "relative/path", "/", "/srv/../root", "/srv/./backups"])
def test_remote_path_rejects_unsafe_scope(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_remote_path(value)


def test_remote_path_and_frappe_artifact_names_are_normalized() -> None:
    assert normalize_remote_path("/srv/almadina/backups/") == "/srv/almadina/backups"
    assert backup_group_identifier(
        "20261008_020000-site_local-database.sql.gz",
        "site_local",
    ) == "20261008_020000-site_local"
    assert backup_group_identifier("../../site_config.json", "site_local") is None
    assert backup_group_identifier(
        "20261008_020000-site_local-partial-database.sql.gz",
        "site_local",
    ) is None


def test_retention_keeps_newest_identifiers_only() -> None:
    assert retention_candidates(
        ["20261001_000000-site", "20261003_000000-site", "20261002_000000-site"],
        2,
    ) == ("20261001_000000-site",)
    with pytest.raises(ValueError):
        retention_candidates(["one"], 0)
