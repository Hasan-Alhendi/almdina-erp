from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle
from almdina_erp.almdina_erp.domain.backups.schedule_reliability import (
    RESTORE_PREPARED_STALE_AFTER,
    is_stale_backup_operation,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.backups import restore as restore_mod
from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory
from almdina_erp.almdina_erp.services import backup_restore_service as service


def _bundle(identifier: str = "20261108_120000-site_local", size: int = 100) -> BackupBundle:
    artifacts = tuple(
        BackupArtifact(
            kind=kind,
            path=f"/tmp/{identifier}-{suffix}",
            filename=f"{identifier}-{suffix}",
            size=size,
            checksum="a" * 64,
        )
        for kind, suffix in (
            ("database", "database.sql.gz"),
            ("public_files", "files.tgz"),
            ("private_files", "private-files.tgz"),
            ("site_config", "site_config_backup.json"),
        )
    )
    return BackupBundle(identifier=identifier, artifacts=artifacts)


def test_restorable_types_include_imported_not_external() -> None:
    assert "Imported" in FrappeBackupHistory.RESTORABLE_OPERATION_TYPES
    assert "External" not in FrappeBackupHistory.RESTORABLE_OPERATION_TYPES
    assert set(FrappeBackupHistory.RESTORABLE_OPERATION_TYPES) == {
        "Manual",
        "Scheduled",
        "Safety",
        "Imported",
    }


def test_prepared_restore_uses_extended_stale_window() -> None:
    now = datetime(2026, 11, 8, 12, 0, 0)
    started = now - timedelta(hours=10)
    assert not is_stale_backup_operation(
        status="Prepared",
        requested_on=started,
        started_on=started,
        now=now,
        prepared_limit=RESTORE_PREPARED_STALE_AFTER,
    )
    assert is_stale_backup_operation(
        status="Prepared",
        requested_on=started,
        started_on=now - RESTORE_PREPARED_STALE_AFTER - timedelta(minutes=1),
        now=now,
        prepared_limit=RESTORE_PREPARED_STALE_AFTER,
    )


def test_request_restore_rejects_concurrent_active_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    class History:
        def has_active_restore(self) -> bool:
            return True

        def resolve_local_bundle(self, *_args: Any, **_kwargs: Any) -> BackupBundle:
            raise AssertionError("must not resolve while another restore is active")

    monkeypatch.setattr(service, "require_doctype_capability", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "restore_runtime_ready", lambda: True)
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "_", lambda message: message)

    def throw(message: str, *_args: Any, **_kwargs: Any) -> None:
        raise ValueError(message)

    monkeypatch.setattr(service.frappe, "throw", throw)
    monkeypatch.setattr(service.frappe, "ValidationError", ValueError)

    with pytest.raises(ValueError, match="already in progress"):
        service.request_restore("source-op", "RESTORE anything")


def test_request_restore_rejects_when_disk_preflight_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class History:
        def has_active_restore(self) -> bool:
            return False

        def resolve_local_bundle(self, operation_id: str) -> BackupBundle:
            assert operation_id == "imported-op"
            return _bundle()

    monkeypatch.setattr(service, "require_doctype_capability", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "restore_runtime_ready", lambda: True)
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(
        service,
        "assert_restore_preflight",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("restore_insufficient_disk_space")),
    )
    monkeypatch.setattr(service, "_", lambda message: message)

    def throw(message: str, *_args: Any, **_kwargs: Any) -> None:
        raise ValueError(message)

    monkeypatch.setattr(service.frappe, "throw", throw)
    monkeypatch.setattr(service.frappe, "ValidationError", ValueError)

    with pytest.raises(ValueError, match="free disk space"):
        service.request_restore("imported-op", "RESTORE 20261108_120000-site_local")


def test_request_restore_accepts_imported_after_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}
    enqueued: list[str] = []

    class History:
        def has_active_restore(self) -> bool:
            return False

        def resolve_local_bundle(self, operation_id: str) -> BackupBundle:
            assert operation_id == "imported-op"
            return _bundle()

        def create(self, **values: Any) -> str:
            created.update(values)
            return "restore-op-1"

        def mark_failed(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("should not fail")

    monkeypatch.setattr(service, "require_doctype_capability", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "restore_runtime_ready", lambda: True)
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "assert_restore_preflight", lambda **_kwargs: None)
    monkeypatch.setattr(service.frappe, "session", SimpleNamespace(user="Administrator"), raising=False)
    monkeypatch.setattr(
        service.frappe,
        "enqueue",
        lambda *args, **kwargs: enqueued.append(kwargs.get("operation_id") or args[0]),
    )
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    result = service.request_restore("imported-op", "RESTORE 20261108_120000-site_local")
    assert result == {"operation_id": "restore-op-1", "status": "Queued"}
    assert created["source_operation_id"] == "imported-op"
    assert created["operation_type"] == "Restore"
    assert enqueued == ["restore-op-1"]


def test_prepare_restore_job_rejects_external_source(monkeypatch: pytest.MonkeyPatch) -> None:
    failed: list[tuple[str, str]] = []

    class History:
        def get(self, operation_id: str) -> dict[str, Any] | None:
            if operation_id == "restore-op":
                return {
                    "operation_type": "Restore",
                    "status": "Queued",
                    "source_operation_id": "external-op",
                    "requested_by": "Administrator",
                    "requested_on": "2026-11-08 12:00:00",
                }
            if operation_id == "external-op":
                return {
                    "operation_type": "Scheduled",
                    "target": "External",
                    "status": "Completed",
                }
            return None

        def mark_running(self, operation_id: str) -> None:
            assert operation_id == "restore-op"

        def mark_failed(self, operation_id: str, error_code: str, **_kwargs: Any) -> None:
            failed.append((operation_id, str(error_code)))

        def resolve_local_bundle(self, *_args: Any, **_kwargs: Any) -> BackupBundle:
            raise AssertionError("external must not resolve")

    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "restore_runtime_ready", lambda: True)
    monkeypatch.setattr(service.frappe, "db", SimpleNamespace(commit=lambda: None))

    service.prepare_restore_job("restore-op")
    assert failed == [("restore-op", "restore_external_not_supported")]


def test_assert_restore_preflight_checks_disk(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(restore_mod, "restore_runtime_ready", lambda: True)
    monkeypatch.setattr(
        restore_mod.frappe,
        "get_site_path",
        lambda *parts: str(tmp_path.joinpath(*parts)) if parts else str(tmp_path),
    )
    monkeypatch.setattr(
        restore_mod.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=100),
    )
    with pytest.raises(ValueError, match="restore_insufficient_disk_space"):
        restore_mod.assert_restore_preflight(required_bytes=1000)


def test_redact_restore_request_credentials(tmp_path: Path) -> None:
    path = tmp_path / "op.json"
    path.write_text(
        json.dumps(
            {
                "db_root": {
                    "db_type": "mariadb",
                    "username": "root",
                    "password": "secret-value",
                }
            }
        ),
        encoding="utf-8",
    )
    assert restore_mod.redact_restore_request_credentials(path) is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["db_root"] == {"db_type": "mariadb", "redacted": True}
    assert restore_mod.redact_restore_request_credentials(path) is False


def test_ui_surfaces_imported_restore_and_site_config_note() -> None:
    root = Path(__file__).resolve().parents[1]
    renderer = (root / "public" / "js" / "factory_production_settings" / "renderer.js").read_text(
        encoding="utf-8"
    )
    dialogs = (root / "public" / "js" / "factory_production_settings" / "dialogs.js").read_text(
        encoding="utf-8"
    )
    assert "Imported backups can be restored" in renderer or "Imported" in renderer
    assert "never restored directly" in renderer
    assert "site_config backup is verified" in dialogs
    assert "not automatically applied" in dialogs


def test_request_restore_still_requires_restore_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[str] = []

    def deny(capability: str, **_kwargs: Any) -> None:
        checked.append(capability)
        raise PermissionError("denied")

    monkeypatch.setattr(service, "require_doctype_capability", deny)
    with pytest.raises(PermissionError):
        service.request_restore("op", "RESTORE x")
    assert checked == [Capability.RESTORE_BACKUPS]
