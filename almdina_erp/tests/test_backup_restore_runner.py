from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.infrastructure.backups.restore_runner import execute_restore, finalize_restore
from almdina_erp.almdina_erp.infrastructure.backups import restore_state


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_bundle(root: Path, stamp: str, site_slug: str) -> dict[str, object]:
    suffixes = {
        "database": "database.sql.gz",
        "public_files": "files.tgz",
        "private_files": "private-files.tgz",
        "site_config": "site_config_backup.json",
    }
    paths: dict[str, str] = {}
    manifest: list[dict[str, object]] = []
    for kind, suffix in suffixes.items():
        path = root / f"{stamp}-{site_slug}-{suffix}"
        path.write_bytes(f"{stamp}:{kind}".encode())
        paths[kind] = str(path)
        manifest.append(
            {
                "kind": kind,
                "filename": path.name,
                "size": path.stat().st_size,
                "checksum": checksum(path),
            }
        )
    return {
        "identifier": f"{stamp}-{site_slug}",
        "paths": paths,
        "manifest": manifest,
        "total_size": sum(int(row["size"]) for row in manifest),
    }


def request_file(tmp_path: Path) -> Path:
    bench = tmp_path / "bench"
    site = "site.local"
    backups = bench / "sites" / site / "private" / "backups"
    requests = bench / "sites" / site / "private" / "backup_restore_requests"
    backups.mkdir(parents=True)
    requests.mkdir(parents=True)
    payload = {
        "version": 1,
        "site": site,
        "bench_path": str(bench),
        "python": sys.executable,
        "operation_id": "restore-op",
        "source_operation_id": "source-op",
        "source_operation_type": "Manual",
        "source_requested_by": "original@example.com",
        "source_requested_on": "2026-10-01 02:00:00",
        "source_completed_on": "2026-10-01 02:05:00",
        "requested_by": "backup@example.com",
        "requested_on": "2026-10-08 02:00:00",
        "safety_operation_id": "safety-op",
        "target": make_bundle(backups, "20261001_020000", "site_local"),
        "safety": make_bundle(backups, "20261008_020000", "site_local"),
    }
    path = requests / "restore-op.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    restore_state.claim(bench / "sites" / site, site, "restore-op")
    restore_state.advance(bench / "sites" / site, "restore-op", "SAFETY_BACKUP")
    return path


def test_restore_uses_frappe_restore_then_migrate_and_finalize(tmp_path: Path) -> None:
    path = request_file(tmp_path)
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> None:
        calls.append(command)

    assert execute_restore(str(path), runner=runner, settle_seconds=0) == 0
    restore_call = next(call for call in calls if "restore" in call)
    assert "--with-public-files" in restore_call
    assert "--with-private-files" in restore_call
    assert "--force" not in restore_call
    assert any("migrate" in call for call in calls)
    assert any("clear-cache" in call for call in calls)
    assert any("finalize_restore" in " ".join(call) for call in calls)
    assert restore_state.read(path.parent.parent.parent)["phase"] == "COMPLETED"


def test_failed_target_restore_uses_safety_backup_before_finalizing(tmp_path: Path) -> None:
    path = request_file(tmp_path)
    payload = json.loads(path.read_text())
    target_database = payload["target"]["paths"]["database"]
    safety_database = payload["safety"]["paths"]["database"]
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> None:
        calls.append(command)
        if "restore" in command and target_database in command:
            raise subprocess.CalledProcessError(1, command)

    assert execute_restore(str(path), runner=runner, settle_seconds=0) == 1
    restore_calls = [command for command in calls if "restore" in command]
    assert target_database in restore_calls[0]
    assert safety_database in restore_calls[1]
    assert any("restore_failed_safety_recovery_completed" in " ".join(call) for call in calls)
    assert restore_state.read(path.parent.parent.parent)["phase"] == "RECOVERED_AFTER_FAILURE"


def test_restore_rejects_artifact_outside_site_backup_scope(tmp_path: Path) -> None:
    path = request_file(tmp_path)
    payload = json.loads(path.read_text())
    outside = tmp_path / "outside.sql.gz"
    outside.write_bytes(b"outside")
    payload["target"]["paths"]["database"] = str(outside)
    row = next(row for row in payload["target"]["manifest"] if row["kind"] == "database")
    row.update(filename=outside.name, size=outside.stat().st_size, checksum=checksum(outside))
    path.write_text(json.dumps(payload), encoding="utf-8")

    calls: list[list[str]] = []
    assert execute_restore(str(path), runner=lambda command, **_kwargs: calls.append(command), settle_seconds=0) == 1
    assert not any("restore" in command for command in calls)
    assert restore_state.read(path.parent.parent.parent)["phase"] == "RECOVERED_AFTER_FAILURE"


def test_failed_restore_and_recovery_leave_site_in_maintenance(tmp_path: Path) -> None:
    path = request_file(tmp_path)
    calls: list[list[str]] = []

    def fail_restore(command: list[str], **_kwargs: object) -> None:
        calls.append(command)
        if "restore" in command:
            raise subprocess.CalledProcessError(1, command)

    assert execute_restore(str(path), runner=fail_restore, settle_seconds=0) == 2
    assert restore_state.read(path.parent.parent.parent)["phase"] == "MANUAL_INTERVENTION_REQUIRED"
    assert not any("off" in command for command in calls)


def test_successful_restore_replaces_old_files_instead_of_merging(tmp_path: Path) -> None:
    path = request_file(tmp_path)
    site = path.parent.parent.parent
    for kind in ("public", "private"):
        folder = site / kind / "files"
        folder.mkdir(parents=True)
        (folder / "old.txt").write_text("old")

    def runner(command: list[str], **_kwargs: object) -> None:
        if "restore" in command:
            for kind in ("public", "private"):
                folder = site / kind / "files"
                folder.mkdir(parents=True)
                (folder / "new.txt").write_text("new")

    assert execute_restore(str(path), runner=runner, settle_seconds=0) == 0
    for kind in ("public", "private"):
        assert sorted(p.name for p in (site / kind / "files").iterdir()) == ["new.txt"]


def test_finalize_keeps_imported_backup_record_after_database_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import frappe

    path = request_file(tmp_path)
    payload = json.loads(path.read_text())
    payload.update(source_operation_type="Imported", source_app_versions='{"frappe":"16.17.5"}')
    path.write_text(json.dumps(payload))
    records: dict[str, dict] = {}

    class Database:
        def exists(self, _doctype: str, operation_id: str) -> bool:
            return operation_id in records

        def set_value(self, _doctype: str, operation_id: str, values: dict, **_kwargs: object) -> None:
            records[operation_id].update(values)

        def commit(self) -> None:
            pass

    def get_doc(values: dict) -> SimpleNamespace:
        def insert(**_kwargs: object) -> None:
            records[values["operation_id"]] = dict(values)
        return SimpleNamespace(insert=insert)

    monkeypatch.setattr(frappe, "local", SimpleNamespace(site="site.local"), raising=False)
    monkeypatch.setattr(frappe.utils, "now", lambda: "2026-11-08 00:00:00")
    monkeypatch.setattr(frappe, "db", Database(), raising=False)
    monkeypatch.setattr(frappe, "get_doc", get_doc, raising=False)
    monkeypatch.setattr(frappe, "get_site_path", lambda *parts: str(path.parent) if parts else str(path.parent.parent.parent), raising=False)
    finalize_restore(str(path), "Completed")
    assert records["source-op"]["operation_type"] == "Imported"
    assert records["source-op"]["import_app_versions"] == payload["source_app_versions"]
    assert records["safety-op"]["status"] == "Completed"
    assert records["restore-op"]["status"] == "Completed"
    assert not path.exists()
