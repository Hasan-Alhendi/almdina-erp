from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.backups.management import BackupBundle
from almdina_erp.almdina_erp.infrastructure.backups.db_root import (
    credentials_payload,
    resolve_effective_db_root,
    restore_runtime_ready,
)
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import bundle_manifest


REQUEST_VERSION = 2
REQUEST_FOLDER = "backup_restore_requests"
# Keep headroom beyond the selected backup size for the Safety Backup artifacts.
DISK_SAFETY_MARGIN_BYTES = 512 * 1024 * 1024


def _bundle_payload(bundle: BackupBundle) -> dict[str, Any]:
    manifest = bundle_manifest(bundle)
    by_kind = {artifact.kind: artifact for artifact in bundle.artifacts}
    return {
        "identifier": bundle.identifier,
        "manifest": manifest,
        "paths": {kind: artifact.path for kind, artifact in by_kind.items()},
        "total_size": bundle.total_size,
    }


def restore_request_path(operation_id: str) -> Path:
    return Path(frappe.get_site_path("private", REQUEST_FOLDER, f"{operation_id}.json")).resolve()


def redact_restore_request_credentials(request_path: str | Path) -> bool:
    """Remove db_root secrets from a restore request file. Never logs secret values."""

    path = Path(request_path)
    try:
        if not path.is_file():
            return False
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return False
        raw = payload.get("db_root")
        if not isinstance(raw, dict) or raw.get("redacted"):
            return False
        payload["db_root"] = {"db_type": raw.get("db_type"), "redacted": True}
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return True
    except Exception:
        return False


def assert_restore_preflight(*, required_bytes: int) -> None:
    """Fail closed when DB root is incomplete or free disk is insufficient for Safety Backup."""

    if not restore_runtime_ready():
        raise ValueError("restore_runtime_not_configured")
    private_root = Path(frappe.get_site_path("private")).resolve()
    private_root.mkdir(parents=True, exist_ok=True)
    free = int(shutil.disk_usage(str(private_root)).free)
    needed = max(int(required_bytes or 0) * 2, int(required_bytes or 0) + DISK_SAFETY_MARGIN_BYTES)
    if free < needed:
        raise ValueError("restore_insufficient_disk_space")


def write_restore_request(
    *,
    operation_id: str,
    source_operation_id: str,
    source_operation_type: str,
    source_requested_by: str,
    source_requested_on: str,
    source_completed_on: str,
    requested_by: str,
    requested_on: str,
    target: BackupBundle,
    safety_operation_id: str,
    safety: BackupBundle,
) -> Path:
    connection = resolve_effective_db_root()
    if not restore_runtime_ready():
        raise ValueError("Restore database credentials are incomplete.")

    folder = Path(frappe.get_site_path("private", REQUEST_FOLDER)).resolve()
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    request_path = folder / f"{operation_id}.json"
    payload = {
        "version": REQUEST_VERSION,
        "site": str(frappe.local.site),
        "bench_path": frappe.utils.get_bench_path(),
        "python": sys.executable,
        "operation_id": operation_id,
        "source_operation_id": source_operation_id,
        "source_operation_type": source_operation_type,
        "source_requested_by": source_requested_by,
        "source_requested_on": source_requested_on,
        "source_completed_on": source_completed_on,
        "requested_by": requested_by,
        "requested_on": requested_on,
        "safety_operation_id": safety_operation_id,
        "target": _bundle_payload(target),
        "safety": _bundle_payload(safety),
        "db_root": credentials_payload(connection),
    }
    request_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.chmod(request_path, stat.S_IRUSR | stat.S_IWUSR)
    return request_path


def launch_restore_runner(request_path: Path) -> int:
    resolved = request_path.resolve()
    log_path = resolved.with_suffix(".log")
    log_stream = log_path.open("ab", buffering=0)
    os.chmod(log_path, stat.S_IRUSR | stat.S_IWUSR)
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "almdina_erp.almdina_erp.infrastructure.backups.restore_runner",
                str(resolved),
            ],
            cwd=frappe.utils.get_bench_path(),
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log_stream.close()
    return int(process.pid)


__all__ = [
    "DISK_SAFETY_MARGIN_BYTES",
    "REQUEST_FOLDER",
    "REQUEST_VERSION",
    "assert_restore_preflight",
    "launch_restore_runner",
    "redact_restore_request_credentials",
    "restore_request_path",
    "restore_runtime_ready",
    "write_restore_request",
]
