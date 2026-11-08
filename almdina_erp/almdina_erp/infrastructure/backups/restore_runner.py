from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


SUPPORTED_REQUEST_VERSIONS = frozenset({1, 2})


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_request(path: str) -> dict[str, Any]:
    request_path = Path(path).resolve(strict=True)
    if request_path.suffix != ".json" or request_path.parent.name != "backup_restore_requests":
        raise ValueError("Restore request path is invalid.")
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") not in SUPPORTED_REQUEST_VERSIONS:
        raise ValueError("Restore request format is invalid.")
    bench_path = Path(str(payload.get("bench_path") or "")).resolve(strict=True)
    site = str(payload.get("site") or "").strip()
    expected_parent = (bench_path / "sites" / site / "private" / "backup_restore_requests").resolve()
    if request_path.parent != expected_parent:
        raise ValueError("Restore request is outside the site scope.")
    return payload


def _validate_bundle(payload: dict[str, Any], backup_root: Path) -> dict[str, str]:
    paths = payload.get("paths")
    manifest = payload.get("manifest")
    if not isinstance(paths, dict) or not isinstance(manifest, list):
        raise ValueError("Restore bundle is invalid.")
    required = {"database", "public_files", "private_files", "site_config"}
    if set(paths) != required:
        raise ValueError("Restore bundle is incomplete.")
    manifest_by_kind = {
        str(row.get("kind") or ""): row
        for row in manifest
        if isinstance(row, dict)
    }
    if set(manifest_by_kind) != required:
        raise ValueError("Restore manifest is incomplete.")
    validated: dict[str, str] = {}
    for kind in required:
        path = Path(str(paths[kind] or "")).resolve(strict=True)
        try:
            path.relative_to(backup_root)
        except ValueError as exc:
            raise ValueError("Restore artifact is outside the backup scope.") from exc
        row = manifest_by_kind[kind]
        if path.name != str(row.get("filename") or ""):
            raise ValueError("Restore artifact filename is invalid.")
        if path.stat().st_size != int(row.get("size") or 0):
            raise ValueError("Restore artifact size is invalid.")
        if _checksum(path) != str(row.get("checksum") or ""):
            raise ValueError("Restore artifact checksum is invalid.")
        validated[kind] = str(path)
    return validated


def _bench_command(payload: dict[str, Any], *arguments: str) -> list[str]:
    return [
        str(payload["python"]),
        "-m",
        "frappe.utils.bench_helper",
        "frappe",
        "--site",
        str(payload["site"]),
        *arguments,
    ]


def _legacy_restore_command(payload: dict[str, Any], bundle: dict[str, str]) -> list[str]:
    """Version-1 compatibility path: relies on Frappe operational conf only."""

    return _bench_command(
        payload,
        "restore",
        bundle["database"],
        "--with-public-files",
        bundle["public_files"],
        "--with-private-files",
        bundle["private_files"],
        "--force",
    )


def _db_root_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("db_root")
    if not isinstance(raw, dict):
        return None
    db_type = str(raw.get("db_type") or "").strip().lower()
    if db_type == "sqlite":
        return {"db_type": "sqlite"}
    username = str(raw.get("username") or "").strip()
    password = str(raw.get("password") or "")
    host = str(raw.get("host") or "").strip()
    try:
        port = int(raw.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    if not (db_type and username and password and host and 1 <= port <= 65535):
        raise ValueError("Restore database credentials are incomplete.")
    return {
        "db_type": db_type,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
    }


def _run(
    command: list[str],
    *,
    cwd: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    runner(command, cwd=str(cwd), check=True, stdin=subprocess.DEVNULL)


def _run_restore_with_credentials(
    payload: dict[str, Any],
    bundle: dict[str, str],
    db_root: dict[str, Any],
    *,
    sites_path: Path,
    runner: Callable[..., Any] | None = None,
) -> None:
    """Restore without placing the root password on a process command line."""

    if runner is not None:
        # Tests inject a command runner; keep the privileged argv free of secrets.
        command = _legacy_restore_command(payload, bundle)
        if "--db-root-password" in command or any(
            str(db_root.get("password") or "") and str(db_root.get("password")) in part
            for part in command
        ):
            raise AssertionError("Restore command must not include the DB root password.")
        _run(command, cwd=sites_path, runner=runner)
        return

    if db_root.get("db_type") == "sqlite":
        _run(_legacy_restore_command(payload, bundle), cwd=sites_path)
        return

    import frappe
    from frappe.commands.site import _restore

    frappe.init(site=str(payload["site"]), sites_path=str(sites_path))
    original_host = frappe.conf.db_host
    original_port = frappe.conf.db_port
    try:
        frappe.conf.db_host = db_root["host"]
        frappe.conf.db_port = db_root["port"]
        try:
            _restore(
                site=str(payload["site"]),
                sql_file_path=bundle["database"],
                db_root_username=db_root["username"],
                db_root_password=db_root["password"],
                force=True,
                with_public_files=bundle["public_files"],
                with_private_files=bundle["private_files"],
            )
        except SystemExit as exc:
            code = int(exc.code or 0) if not isinstance(exc.code, str) else 1
            if code != 0:
                raise RuntimeError("restore_failed") from exc
    finally:
        frappe.conf.db_host = original_host
        frappe.conf.db_port = original_port
        frappe.flags.root_login = None
        frappe.flags.root_password = None
        if getattr(frappe.local, "flags", None) is not None:
            frappe.local.flags.root_connection = None
        try:
            frappe.destroy()
        except Exception:
            pass


def _verify_commands(payload: dict[str, Any]) -> list[str]:
    return _bench_command(
        payload,
        "execute",
        "almdina_erp.almdina_erp.infrastructure.backups.restore_runner.verify_restored_site",
    )


def verify_restored_site() -> None:
    """Practical post-restore checks: DB connectivity and basic site loadability.

    Does not re-apply ``site_config_backup.json`` onto the live site config; that
    remains outside Frappe's standard restore path and is an explicit non-goal.
    """

    import frappe

    if not getattr(frappe.local, "site", None):
        raise RuntimeError("restore_verification_site_missing")
    frappe.connect()
    try:
        frappe.db.sql("select 1")
        # Administrator must resolve after a full-site restore; fail closed otherwise.
        if not frappe.db.get_value("User", "Administrator", "name"):
            raise RuntimeError("restore_verification_admin_missing")
        conf = frappe.get_site_config()
        if not isinstance(conf, dict) or not conf:
            raise RuntimeError("restore_verification_site_config_unreadable")
    finally:
        try:
            frappe.db.close()
        except Exception:
            pass


def execute_restore(
    request_path: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
    settle_seconds: float = 2.0,
) -> int:
    from almdina_erp.almdina_erp.infrastructure.backups.restore import (
        redact_restore_request_credentials,
    )

    payload = _read_request(request_path)
    bench_path = Path(str(payload["bench_path"])).resolve()
    sites_path = (bench_path / "sites").resolve()
    backup_root = (sites_path / str(payload["site"]) / "private" / "backups").resolve()
    target = _validate_bundle(payload["target"], backup_root)
    safety = _validate_bundle(payload["safety"], backup_root)
    db_root = _db_root_from_payload(payload)
    if settle_seconds > 0:
        time.sleep(settle_seconds)

    status = "Completed"
    error_code = ""

    def restore_one(bundle: dict[str, str]) -> None:
        if db_root is not None:
            _run_restore_with_credentials(
                payload,
                bundle,
                db_root,
                sites_path=sites_path,
                runner=runner if runner is not subprocess.run else None,
            )
            return
        _run(_legacy_restore_command(payload, bundle), cwd=sites_path, runner=runner)

    def restore_pipeline(bundle: dict[str, str]) -> None:
        restore_one(bundle)
        _run(_bench_command(payload, "migrate"), cwd=sites_path, runner=runner)
        _run(_bench_command(payload, "clear-cache"), cwd=sites_path, runner=runner)
        _run(_verify_commands(payload), cwd=sites_path, runner=runner)

    try:
        try:
            restore_pipeline(target)
        except Exception:
            status = "Failed"
            error_code = "restore_failed_safety_recovery_started"
            try:
                restore_pipeline(safety)
                error_code = "restore_failed_safety_recovery_completed"
            except Exception:
                error_code = "restore_and_safety_recovery_failed"

        # Drop secrets as soon as restore work finishes, before audit finalize.
        redact_restore_request_credentials(request_path)

        finalize_kwargs = json.dumps(
            {
                "request_path": str(Path(request_path).resolve()),
                "status": status,
                "error_code": error_code,
            },
            separators=(",", ":"),
        )
        try:
            _run(
                _bench_command(
                    payload,
                    "execute",
                    "almdina_erp.almdina_erp.infrastructure.backups.restore_runner.finalize_restore",
                    "--kwargs",
                    finalize_kwargs,
                ),
                cwd=sites_path,
                runner=runner,
            )
        except Exception:
            return 2
        return 0 if status == "Completed" else 1
    finally:
        redact_restore_request_credentials(request_path)


def finalize_restore(request_path: str, status: str, error_code: str = "") -> None:
    """Recreate the restore audit after the selected database is restored."""

    import frappe
    from frappe.utils import now

    from almdina_erp.almdina_erp.infrastructure.backups.history import DOCTYPE
    from almdina_erp.almdina_erp.infrastructure.backups.restore import (
        REQUEST_FOLDER,
        redact_restore_request_credentials,
    )

    path = Path(request_path).resolve(strict=True)
    allowed = Path(frappe.get_site_path("private", REQUEST_FOLDER)).resolve()
    if path.parent != allowed:
        raise ValueError("Restore request is outside the site scope.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("site") != frappe.local.site:
        raise ValueError("Restore request belongs to another site.")

    # Drop privileged credentials from disk as soon as audit finalization starts.
    redact_restore_request_credentials(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    def upsert(operation_id: str, values: dict[str, Any]) -> None:
        if frappe.db.exists(DOCTYPE, operation_id):
            frappe.db.set_value(DOCTYPE, operation_id, values, update_modified=False)
            return
        frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "operation_id": operation_id,
                **values,
            }
        ).insert(ignore_permissions=True)

    def manifest_values(bundle: dict[str, Any]) -> dict[str, Any]:
        manifest = json.dumps(
            bundle["manifest"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "backup_identifier": bundle["identifier"],
            "reference": bundle["identifier"],
            "total_size": int(bundle.get("total_size") or 0),
            "checksum": hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
            "artifact_manifest": manifest,
        }

    restore_common = {
        "requested_by": payload.get("requested_by") or "Administrator",
        "requested_on": payload.get("requested_on") or now(),
        "completed_on": now(),
    }
    upsert(
        payload["source_operation_id"],
        {
            **manifest_values(payload["target"]),
            "requested_by": payload.get("source_requested_by") or "Administrator",
            "requested_on": payload.get("source_requested_on") or payload.get("requested_on") or now(),
            "completed_on": payload.get("source_completed_on") or payload.get("source_requested_on") or now(),
            "operation_type": payload.get("source_operation_type") or "Manual",
            "target": "Local",
            "status": "Completed",
        },
    )
    upsert(
        payload["safety_operation_id"],
        {
            **restore_common,
            **manifest_values(payload["safety"]),
            "operation_type": "Safety",
            "target": "Local",
            "status": "Completed",
        },
    )
    upsert(
        payload["operation_id"],
        {
            **restore_common,
            "operation_type": "Restore",
            "target": "Restore",
            "status": "Completed" if status == "Completed" else "Failed",
            "backup_identifier": payload["target"]["identifier"],
            "reference": payload["source_operation_id"],
            "source_operation_id": payload["source_operation_id"],
            "error_summary": str(error_code or "")[:140] or None,
        },
    )
    frappe.db.commit()
    path.unlink(missing_ok=True)


def main() -> int:
    if len(sys.argv) != 2:
        return 64
    return execute_restore(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["execute_restore", "finalize_restore", "verify_restored_site"]
