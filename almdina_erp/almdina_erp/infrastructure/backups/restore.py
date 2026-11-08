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


def preflight_restore(target: BackupBundle) -> None:
    """Verify prerequisites without changing the site or exposing credentials."""
    if not restore_runtime_ready():
        raise ValueError("restore_runtime_not_configured")
    if not shutil.which("tar") or not shutil.which("gzip"):
        raise ValueError("restore_tools_unavailable")
    site_path = Path(frappe.get_site_path()).resolve()
    # The safety copy and restored files coexist with the selected backup.
    needed = target.total_size * 2 + 512 * 1024 * 1024
    if shutil.disk_usage(site_path).free < needed:
        raise ValueError("restore_disk_space")
    if str(frappe.conf.db_type or "").lower() == "mariadb":
        import pymysql

        options = {"user": frappe.conf.get("mariadb_root_login") or frappe.conf.get("root_login") or "root",
                   "password": frappe.conf.get("mariadb_root_password") or frappe.conf.get("root_password"),
                   "connect_timeout": 5, "read_timeout": 5}
        if frappe.conf.db_socket:
            options["unix_socket"] = frappe.conf.db_socket
        else:
            options.update(host=frappe.conf.db_host or "localhost", port=int(frappe.conf.db_port or 3306))
        try:
            connection = pymysql.connect(**options)
            connection.close()
        except (pymysql.MySQLError, OSError) as exc:
            raise ValueError("restore_db_admin_unavailable") from exc
    elif str(frappe.conf.db_type or "").lower() != "sqlite":
        raise ValueError("restore_db_admin_unavailable")
    try:
        frappe.db.sql("SELECT 1")
    except Exception as exc:
        raise ValueError("restore_db_unavailable") from exc


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
    source_app_versions: str = "",
    previous_maintenance: bool | None = None,
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
        "source_app_versions": source_app_versions,
        "source_requested_by": source_requested_by,
        "source_requested_on": source_requested_on,
        "source_completed_on": source_completed_on,
        "requested_by": requested_by,
        "requested_on": requested_on,
        "safety_operation_id": safety_operation_id,
        "target": _bundle_payload(target),
        "safety": _bundle_payload(safety),
        "previous_maintenance": bool(frappe.conf.get("maintenance_mode") if previous_maintenance is None else previous_maintenance),
        "previous_scheduler_pause": bool(frappe.conf.get("pause_scheduler")),
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
    "preflight_restore",
    "write_restore_request",
]
