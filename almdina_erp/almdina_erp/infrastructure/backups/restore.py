from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.backups.management import BackupBundle
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import bundle_manifest


REQUEST_VERSION = 1
REQUEST_FOLDER = "backup_restore_requests"


def restore_runtime_ready() -> bool:
    db_type = str(frappe.conf.db_type or "").lower()
    if db_type == "sqlite":
        return True
    if db_type == "mariadb":
        return bool(
            frappe.conf.get("mariadb_root_password")
            or frappe.conf.get("root_password")
        )
    if db_type == "postgres":
        return bool(
            frappe.conf.get("postgres_root_password")
            or frappe.conf.get("root_password")
        )
    return False


def _bundle_payload(bundle: BackupBundle) -> dict[str, Any]:
    manifest = bundle_manifest(bundle)
    by_kind = {artifact.kind: artifact for artifact in bundle.artifacts}
    return {
        "identifier": bundle.identifier,
        "manifest": manifest,
        "paths": {kind: artifact.path for kind, artifact in by_kind.items()},
        "total_size": bundle.total_size,
    }


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
    "REQUEST_FOLDER",
    "REQUEST_VERSION",
    "launch_restore_runner",
    "restore_runtime_ready",
    "write_restore_request",
]
