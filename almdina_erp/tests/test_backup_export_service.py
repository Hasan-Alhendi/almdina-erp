from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from almdina_erp.almdina_erp.application.backups.export import PackedBackupExport
from almdina_erp.almdina_erp.domain.backups.export_format import (
    EXPORT_FORMAT,
    EXPORT_FORMAT_VERSION,
    ExportComponent,
    ExportManifest,
)
from almdina_erp.almdina_erp.infrastructure.backups import export_zip as export_mod
from almdina_erp.almdina_erp.infrastructure.backups.export_zip import BackupExportError, annotate_downloadable
from almdina_erp.almdina_erp.services import backup_restore_service as service


class DummyResponse:
    def __init__(self) -> None:
        self.closed = False
        self.close_callbacks: list[Any] = []

    def close(self) -> None:
        self.closed = True
        for callback in list(self.close_callbacks):
            callback()

    def call_on_close(self, callback: Any) -> None:
        self.close_callbacks.append(callback)


def test_annotate_downloadable_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_mod, "_local_backup_identifiers_present", lambda _site: {"id-1"})
    rows = annotate_downloadable(
        [
            {
                "operation_id": "1",
                "status": "Completed",
                "target": "Local",
                "operation_type": "Manual",
                "backup_identifier": "id-1",
            },
            {
                "operation_id": "2",
                "status": "Queued",
                "target": "Local",
                "operation_type": "Manual",
                "backup_identifier": "id-2",
            },
            {
                "operation_id": "3",
                "status": "Running",
                "target": "Local",
                "operation_type": "Manual",
                "backup_identifier": "id-3",
            },
            {
                "operation_id": "4",
                "status": "Failed",
                "target": "Local",
                "operation_type": "Manual",
                "backup_identifier": "id-4",
            },
            {
                "operation_id": "5",
                "status": "Completed",
                "target": "External",
                "operation_type": "Scheduled",
                "backup_identifier": "id-5",
            },
            {
                "operation_id": "6",
                "status": "Completed",
                "target": "Local",
                "operation_type": "Manual",
                "backup_identifier": "missing-on-disk",
            },
        ]
    )
    assert [row["can_download"] for row in rows] == [True, False, False, False, True, False]


@pytest.mark.parametrize(
    "safe_code",
    [
        "backup_export_not_found",
        "backup_export_not_eligible",
        "backup_export_missing_component",
        "backup_export_integrity_failed",
    ],
)
def test_download_backup_zip_maps_safe_failures(
    monkeypatch: pytest.MonkeyPatch,
    safe_code: str,
) -> None:
    thrown: list[str] = []

    def throw(message: str, *_args: Any, **_kwargs: Any) -> None:
        thrown.append(str(message))
        raise service.frappe.ValidationError(message)

    monkeypatch.setattr(service, "require_doctype_capability", lambda *_a, **_k: None)
    monkeypatch.setattr(
        service,
        "build_backup_zip_export",
        lambda *_a, **_k: (_ for _ in ()).throw(BackupExportError(safe_code)),
    )
    monkeypatch.setattr(service, "_", lambda message: message)
    monkeypatch.setattr(service.frappe, "throw", throw)

    with pytest.raises(service.frappe.ValidationError):
        service.download_backup_zip("missing-or-bad")
    assert thrown
    assert "private/" not in thrown[0]
    assert "/home/" not in thrown[0]
    assert ".sql.gz" not in thrown[0]


def test_download_backup_zip_returns_response_without_history_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(b"PK\x03\x04fake")
    packed = PackedBackupExport(
        zip_path=str(zip_path),
        download_name="export.zip",
        manifest=ExportManifest(
            format=EXPORT_FORMAT,
            format_version=EXPORT_FORMAT_VERSION,
            backup_id="id-1",
            operation_id="op-1",
            site="site.local",
            created_at="2026-11-08 12:00:00",
            database_type="mariadb",
            target="Local",
            operation_type="Manual",
            components=(
                ExportComponent("database", "a.sql.gz", 1, "a" * 64),
                ExportComponent("public_files", "b.tgz", 1, "b" * 64),
                ExportComponent("private_files", "c.tgz", 1, "c" * 64),
                ExportComponent("site_config", "d.json", 1, "d" * 64),
            ),
        ),
        cleanup_paths=(str(tmp_path / "staging"),),
    )
    response = DummyResponse()
    history_calls: list[str] = []

    monkeypatch.setattr(service, "require_doctype_capability", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "build_backup_zip_export", lambda *_a, **_k: packed)
    monkeypatch.setattr(service, "send_backup_zip_response", lambda _packed: response)
    monkeypatch.setattr(
        service,
        "FrappeBackupHistory",
        lambda: SimpleNamespace(create=lambda **kwargs: history_calls.append(json.dumps(kwargs))),
    )

    assert service.download_backup_zip("op-1") is response
    assert history_calls == []


def test_get_backup_context_marks_downloadable_when_manage_backups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class History:
        def list_recent(self, _limit: int = 30) -> list[dict[str, Any]]:
            return [
                {
                    "operation_id": "1",
                    "status": "Completed",
                    "target": "Local",
                    "operation_type": "Manual",
                    "backup_identifier": "id-1",
                },
                {
                    "operation_id": "2",
                    "status": "Failed",
                    "target": "Local",
                    "operation_type": "Manual",
                    "backup_identifier": "id-2",
                },
            ]

        def restorable(self, _limit: int = 30) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr(service, "require_any_doctype_capability", lambda *_a, **_k: None)
    monkeypatch.setattr(service, "doctype_has_capability", lambda capability: capability == service.Capability.MANAGE_BACKUPS)
    monkeypatch.setattr(service, "FrappeBackupHistory", History)
    monkeypatch.setattr(service, "restore_runtime_ready", lambda: False)
    monkeypatch.setattr(export_mod, "_local_backup_identifiers_present", lambda _site: {"id-1"})
    monkeypatch.setattr(service, "annotate_downloadable", export_mod.annotate_downloadable)

    payload = service.get_backup_context()
    assert payload["history"][0]["can_download"] is True
    assert payload["history"][1]["can_download"] is False


def test_send_backup_zip_response_registers_after_stream_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    zip_path = staging / "id-1.zip"
    zip_path.write_bytes(b"PK\x03\x04data")
    marker = staging / "keep-until-close.bin"
    marker.write_bytes(b"x")

    packed = PackedBackupExport(
        zip_path=str(zip_path),
        download_name="id-1.zip",
        manifest=ExportManifest(
            format=EXPORT_FORMAT,
            format_version=EXPORT_FORMAT_VERSION,
            backup_id="id-1",
            operation_id="op-1",
            site="site.local",
            created_at="2026-11-08 12:00:00",
            database_type="mariadb",
            target="Local",
            operation_type="Manual",
            components=(
                ExportComponent("database", "a.sql.gz", 1, "a" * 64),
                ExportComponent("public_files", "b.tgz", 1, "b" * 64),
                ExportComponent("private_files", "c.tgz", 1, "c" * 64),
                ExportComponent("site_config", "d.json", 1, "d" * 64),
            ),
        ),
        cleanup_paths=(str(staging),),
    )

    after = SimpleNamespace(callbacks=[])
    after.add = after.callbacks.append  # type: ignore[attr-defined]
    response = DummyResponse()

    monkeypatch.setattr(
        export_mod,
        "send_file",
        lambda *_a, **_k: response,
    )
    monkeypatch.setattr(
        export_mod.frappe,
        "local",
        SimpleNamespace(request=SimpleNamespace(after_response=after, environ={})),
        raising=False,
    )

    result = export_mod.send_backup_zip_response(packed)
    assert result is response
    assert marker.exists()
    assert response.close_callbacks
    assert after.callbacks
    response.close()
    assert not staging.exists()
