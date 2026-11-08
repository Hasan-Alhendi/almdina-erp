from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from almdina_erp.almdina_erp.domain.backups.retry import (
    MAX_BACKUP_ATTEMPTS,
    decide_external_backup_retry,
    is_transient_backup_error,
    retry_delay_seconds_after_attempt,
)
from almdina_erp.almdina_erp.infrastructure.backups.sftp import (
    SFTPGatewayError,
    SSHAuthenticationError,
)
from almdina_erp.almdina_erp.services import backup_restore_service as service


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ssh_connection_failed", True),
        ("ssh_upload_failed", True),
        ("ssh_upload_integrity_failed", True),
        ("TimeoutError", True),
        ("ssh_authentication_failed", False),
        ("ssh_remote_path_invalid", False),
        ("external_backup_disabled", False),
        ("backup_retry_exhausted", False),
    ],
)
def test_transient_and_permanent_error_classification(code: str, expected: bool) -> None:
    assert is_transient_backup_error(code) is expected


def test_retry_delays_and_attempt_cap() -> None:
    assert retry_delay_seconds_after_attempt(1) == 60
    assert retry_delay_seconds_after_attempt(2) == 300
    assert retry_delay_seconds_after_attempt(3) is None

    first = decide_external_backup_retry(attempt=1, error_code="ssh_connection_failed")
    assert first.action == "retry"
    assert first.delay_seconds == 60

    second = decide_external_backup_retry(attempt=2, error_code="ssh_upload_failed")
    assert second.action == "retry"
    assert second.delay_seconds == 300

    third = decide_external_backup_retry(attempt=3, error_code="ssh_connection_failed")
    assert third.action == "fail"
    assert third.delay_seconds is None

    permanent = decide_external_backup_retry(attempt=1, error_code="ssh_authentication_failed")
    assert permanent.action == "fail"
    assert MAX_BACKUP_ATTEMPTS == 3


class FakeSettings:
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self.values = values or {}

    def get(self, fieldname: str, default: Any = None) -> Any:
        return self.values.get(fieldname, default)


def test_external_job_schedules_retry_for_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {"begin": [], "retry": [], "failed": []}

    class History:
        def get(self, operation_id: str) -> dict[str, Any]:
            return {
                "operation_id": operation_id,
                "status": "Queued",
                "target": "External",
                "operation_type": "Scheduled",
                "attempt_count": 0,
                "next_retry_on": None,
            }

        def begin_attempt(self, operation_id: str, attempt: int) -> None:
            calls["begin"].append((operation_id, attempt))

        def schedule_retry(self, operation_id: str, **kwargs: Any) -> datetime:
            calls["retry"].append({"operation_id": operation_id, **kwargs})
            return datetime(2026, 11, 8, 12, 1, 0)

        def mark_failed(self, operation_id: str, error_code: str, **kwargs: Any) -> None:
            calls["failed"].append((operation_id, error_code, kwargs))

    class BoomEngine:
        def create(self):
            from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle

            return BackupBundle(
                "id-1",
                (
                    BackupArtifact("database", "/tmp/x", "x.sql.gz", 1, "a" * 64),
                ),
            )

        def release(self, bundle) -> None:  # noqa: ANN001
            return None

    class TransientUpload(SFTPGatewayError):
        safe_code = "ssh_connection_failed"

    class TransientGateway:
        def upload(self, bundle):  # noqa: ANN001
            raise TransientUpload("down")

        def apply_retention(self, keep_last: int) -> None:
            raise AssertionError("retention must not run")

    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_settings", lambda: FakeSettings({"external_backup_enabled": 1, "external_backup_retention": 4}))
    monkeypatch.setattr(service, "_retention", lambda _settings, _prefix: 4)
    monkeypatch.setattr(service, "_external_backup_gateway", lambda _settings=None: TransientGateway())
    monkeypatch.setattr(service, "FrappeBackupEngine", lambda ephemeral=False: BoomEngine())
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 8, 12, 0, 0))
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    service.run_backup_job("op-1", "external")
    assert calls["begin"] == [("op-1", 1)]
    assert len(calls["retry"]) == 1
    assert calls["retry"][0]["delay_seconds"] == 60
    assert calls["retry"][0]["attempt"] == 1
    assert calls["failed"] == []


def test_external_job_fails_permanently_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {"retry": [], "failed": []}

    class History:
        def get(self, operation_id: str) -> dict[str, Any]:
            return {
                "operation_id": operation_id,
                "status": "Queued",
                "target": "External",
                "operation_type": "Scheduled",
                "attempt_count": 0,
                "next_retry_on": None,
            }

        def begin_attempt(self, operation_id: str, attempt: int) -> None:
            return None

        def schedule_retry(self, *args: Any, **kwargs: Any) -> datetime:
            calls["retry"].append(kwargs)
            return datetime(2026, 11, 8, 12, 1, 0)

        def mark_failed(self, operation_id: str, error_code: str, **kwargs: Any) -> None:
            calls["failed"].append((operation_id, error_code, kwargs.get("attempt")))

    class AuthGateway:
        def upload(self, bundle):  # noqa: ANN001
            raise SSHAuthenticationError("bad key")

        def apply_retention(self, keep_last: int) -> None:
            return None

    class Engine:
        def create(self):
            from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle

            return BackupBundle(
                "id-1",
                (BackupArtifact("database", "/tmp/x", "x.sql.gz", 1, "a" * 64),),
            )

        def release(self, bundle) -> None:  # noqa: ANN001
            return None

    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_settings", lambda: FakeSettings({"external_backup_enabled": 1, "external_backup_retention": 4}))
    monkeypatch.setattr(service, "_retention", lambda *_a: 4)
    monkeypatch.setattr(service, "_external_backup_gateway", lambda _settings=None: AuthGateway())
    monkeypatch.setattr(service, "FrappeBackupEngine", lambda ephemeral=False: Engine())
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 8, 12, 0, 0))
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    with pytest.raises(SSHAuthenticationError):
        service.run_backup_job("op-auth", "external")
    assert calls["retry"] == []
    assert calls["failed"] == [("op-auth", "ssh_authentication_failed", 1)]


def test_external_job_exhausts_retries_on_third_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {"retry": [], "failed": []}

    class History:
        def get(self, operation_id: str) -> dict[str, Any]:
            return {
                "operation_id": operation_id,
                "status": "Queued",
                "target": "External",
                "operation_type": "Scheduled",
                "attempt_count": 2,
                "next_retry_on": datetime(2026, 11, 8, 11, 55, 0),
            }

        def begin_attempt(self, operation_id: str, attempt: int) -> None:
            assert attempt == 3

        def schedule_retry(self, *args: Any, **kwargs: Any) -> datetime:
            calls["retry"].append(kwargs)
            return datetime(2026, 11, 8, 12, 10, 0)

        def mark_failed(self, operation_id: str, error_code: str, **kwargs: Any) -> None:
            calls["failed"].append((operation_id, error_code, kwargs.get("attempt")))

    class Transient(SFTPGatewayError):
        safe_code = "ssh_connection_failed"

    class Gateway:
        def upload(self, bundle):  # noqa: ANN001
            raise Transient("still down")

        def apply_retention(self, keep_last: int) -> None:
            return None

    class Engine:
        def create(self):
            from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle

            return BackupBundle(
                "id-1",
                (BackupArtifact("database", "/tmp/x", "x.sql.gz", 1, "a" * 64),),
            )

        def release(self, bundle) -> None:  # noqa: ANN001
            return None

    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_settings", lambda: FakeSettings({"external_backup_enabled": 1, "external_backup_retention": 4}))
    monkeypatch.setattr(service, "_retention", lambda *_a: 4)
    monkeypatch.setattr(service, "_external_backup_gateway", lambda _settings=None: Gateway())
    monkeypatch.setattr(service, "FrappeBackupEngine", lambda ephemeral=False: Engine())
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 8, 12, 0, 0))
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    with pytest.raises(Transient):
        service.run_backup_job("op-3", "external")
    assert calls["retry"] == []
    assert calls["failed"] == [("op-3", "ssh_connection_failed", 3)]


def test_scheduler_enqueues_due_external_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: list[tuple[str, str]] = []

    class History:
        def reclaim_stale_operations(self, *, now=None) -> int:
            return 0

        def due_external_retries(self, *, now=None) -> list[dict[str, Any]]:
            return [{"operation_id": "retry-op", "attempt_count": 1, "next_retry_on": now}]

        def exists_for_schedule(self, _schedule_key: str) -> bool:
            return True

        def create(self, **values: Any) -> str:
            raise AssertionError("must not create a new operation for retries")

    monkeypatch.setattr(service, "_settings", lambda: FakeSettings({"local_backup_enabled": 0, "external_backup_enabled": 0}))
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 8, 12, 0, 0))
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(
        service,
        "_enqueue_backup",
        lambda operation_id, target: enqueued.append((operation_id, target)),
    )
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    service.scheduled_backup_tick()
    assert enqueued == [("retry-op", "external")]


def test_external_job_skips_future_retry_window(monkeypatch: pytest.MonkeyPatch) -> None:
    began = []

    class History:
        def get(self, operation_id: str) -> dict[str, Any]:
            return {
                "operation_id": operation_id,
                "status": "Queued",
                "target": "External",
                "operation_type": "Scheduled",
                "attempt_count": 1,
                "next_retry_on": datetime(2026, 11, 8, 12, 5, 0),
            }

        def begin_attempt(self, operation_id: str, attempt: int) -> None:
            began.append((operation_id, attempt))

    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_settings", lambda: FakeSettings({"external_backup_enabled": 1}))
    monkeypatch.setattr(service, "now_datetime", lambda: datetime(2026, 11, 8, 12, 0, 0))
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    service.run_backup_job("op-wait", "external")
    assert began == []
