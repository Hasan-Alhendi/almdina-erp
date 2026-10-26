from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from almdina_erp.almdina_erp.infrastructure.backups.restore_runner import execute_restore


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
    return path


def test_restore_uses_frappe_restore_then_migrate_and_finalize(tmp_path: Path) -> None:
    path = request_file(tmp_path)
    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> None:
        calls.append(command)

    assert execute_restore(str(path), runner=runner, settle_seconds=0) == 0
    assert "restore" in calls[0]
    assert "--with-public-files" in calls[0]
    assert "--with-private-files" in calls[0]
    assert "migrate" in calls[1]
    assert "clear-cache" in calls[2]
    assert "finalize_restore" in " ".join(calls[3])


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
    assert "restore_failed_safety_recovery_completed" in " ".join(calls[-1])


def test_restore_rejects_artifact_outside_site_backup_scope(tmp_path: Path) -> None:
    path = request_file(tmp_path)
    payload = json.loads(path.read_text())
    outside = tmp_path / "outside.sql.gz"
    outside.write_bytes(b"outside")
    payload["target"]["paths"]["database"] = str(outside)
    row = next(row for row in payload["target"]["manifest"] if row["kind"] == "database")
    row.update(filename=outside.name, size=outside.stat().st_size, checksum=checksum(outside))
    path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        execute_restore(str(path), runner=lambda *_args, **_kwargs: None, settle_seconds=0)
    except ValueError as exc:
        assert "outside the backup scope" in str(exc)
    else:
        raise AssertionError("outside restore artifact was accepted")
