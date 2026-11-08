from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from almdina_erp.almdina_erp.domain.backups.schedule_reliability import (
    QUEUED_STALE_AFTER,
    RUNNING_STALE_AFTER,
    is_stale_backup_operation,
)
from almdina_erp.almdina_erp.services import backup_restore_service as service


class FakeSettings:
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values = values or {}

    def get(self, fieldname: str, default: Any = None) -> Any:
        return self.values.get(fieldname, default)


def test_queued_and_running_stale_detection() -> None:
    now = datetime(2026, 11, 7, 12, 0, 0)
    assert is_stale_backup_operation(
        status="Queued",
        requested_on=now - QUEUED_STALE_AFTER - timedelta(minutes=1),
        started_on=None,
        now=now,
    )
    assert not is_stale_backup_operation(
        status="Queued",
        requested_on=now - timedelta(minutes=5),
        started_on=None,
        now=now,
    )
    assert is_stale_backup_operation(
        status="Running",
        requested_on=now - timedelta(hours=1),
        started_on=now - RUNNING_STALE_AFTER - timedelta(minutes=1),
        now=now,
    )
    assert not is_stale_backup_operation(
        status="Completed",
        requested_on=now - timedelta(days=1),
        started_on=now - timedelta(days=1),
        now=now,
    )


def test_scheduler_marks_enqueue_failure_and_allows_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = FakeSettings(
        {
            "local_backup_enabled": 1,
            "external_backup_enabled": 0,
            "local_backup_frequency": "Daily",
            "local_backup_time": "02:00",
        }
    )
    created: list[str] = []
    failed: list[tuple[str, str]] = []
    exists = {"value": False}

    class History:
        def reclaim_stale_operations(self, *, now=None) -> int:
            return 0

        def due_external_retries(self, *, now=None) -> list[dict[str, Any]]:
            return []

        def exists_for_schedule(self, schedule_key: str) -> bool:
            return exists["value"]

        def create(self, **values: Any) -> str:
            created.append(values["schedule_key"])
            return "op-local"

        def mark_failed(self, operation_id: str, error_code: str, **_kwargs: Any) -> None:
            failed.append((operation_id, error_code))
            exists["value"] = False

    def boom(_operation_id: str, _target: str) -> None:
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(service, "_settings", lambda: settings)
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 7, 2, 0))
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_enqueue_backup", boom)
    monkeypatch.setattr(service.frappe, "db", type("DB", (), {"commit": staticmethod(lambda: None)})())
    monkeypatch.setattr(service.frappe, "logger", lambda _name: type("L", (), {"error": staticmethod(lambda *a, **k: None)})())

    service.scheduled_backup_tick()

    assert created == ["local:daily:2026-11-07"]
    assert failed == [("op-local", "backup_enqueue_failed")]


def test_scheduler_skips_active_schedule_but_not_after_failed_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = FakeSettings(
        {
            "local_backup_enabled": 1,
            "external_backup_enabled": 0,
            "local_backup_frequency": "Daily",
            "local_backup_time": "02:00",
        }
    )
    enqueued: list[str] = []
    blocking = {"value": True}

    class History:
        def reclaim_stale_operations(self, *, now=None) -> int:
            return 0

        def due_external_retries(self, *, now=None) -> list[dict[str, Any]]:
            return []

        def exists_for_schedule(self, _schedule_key: str) -> bool:
            return blocking["value"]

        def create(self, **values: Any) -> str:
            return "op-2"

    monkeypatch.setattr(service, "_settings", lambda: settings)
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 7, 2, 0))
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_enqueue_backup", lambda operation_id, target: enqueued.append(target))
    monkeypatch.setattr(service.frappe, "db", type("DB", (), {"commit": staticmethod(lambda: None)})())

    service.scheduled_backup_tick()
    assert enqueued == []

    blocking["value"] = False
    service.scheduled_backup_tick()
    assert enqueued == ["local"]


def test_scheduler_reclaims_stale_before_creating(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = FakeSettings(
        {
            "local_backup_enabled": 1,
            "external_backup_enabled": 0,
            "local_backup_frequency": "Daily",
            "local_backup_time": "02:00",
        }
    )
    events: list[str] = []

    class History:
        def reclaim_stale_operations(self, *, now=None) -> int:
            events.append("reclaim")
            return 1

        def due_external_retries(self, *, now=None) -> list[dict[str, Any]]:
            events.append("retries")
            return []

        def exists_for_schedule(self, _schedule_key: str) -> bool:
            events.append("exists")
            return False

        def create(self, **values: Any) -> str:
            events.append("create")
            return "op-3"

    monkeypatch.setattr(service, "_settings", lambda: settings)
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 7, 2, 0))
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_enqueue_backup", lambda *_args, **_kwargs: events.append("enqueue"))
    monkeypatch.setattr(service.frappe, "db", type("DB", (), {"commit": staticmethod(lambda: None)})())

    service.scheduled_backup_tick()
    assert events[:3] == ["reclaim", "retries", "exists"]
    assert "create" in events and "enqueue" in events
