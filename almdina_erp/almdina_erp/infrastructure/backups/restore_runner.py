from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from almdina_erp.almdina_erp.infrastructure.backups import restore_state


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
    if not isinstance(payload, dict) or payload.get("version") != 1:
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


def _restore_command(payload: dict[str, Any], bundle: dict[str, str]) -> list[str]:
    return _bench_command(
        payload,
        "restore",
        bundle["database"],
        "--with-public-files",
        bundle["public_files"],
        "--with-private-files",
        bundle["private_files"],
    )


def _run(
    command: list[str],
    *,
    cwd: Path,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    runner(command, cwd=str(cwd), check=True, stdin=subprocess.DEVNULL)


def execute_restore(
    request_path: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
    settle_seconds: float = 2.0,
) -> int:
    payload = _read_request(request_path)
    bench_path = Path(str(payload["bench_path"])).resolve()
    sites_path = (bench_path / "sites").resolve()
    backup_root = (sites_path / str(payload["site"]) / "private" / "backups").resolve()
    site_path = sites_path / str(payload["site"])
    operation_id = str(payload["operation_id"])
    state = restore_state.read(site_path)
    if state.get("operation_id") != operation_id or state.get("phase") != "SAFETY_BACKUP":
        raise ValueError("Restore runner was not prepared for this site.")
    restore_state.advance(site_path, operation_id, "MAINTENANCE", runner_pid=os.getpid())
    destructive = False
    staged = False
    status = "Failed"
    error_code = "restore_failed_safety_recovery_started"
    try:
        target = _validate_bundle(payload["target"], backup_root)
        safety = _validate_bundle(payload["safety"], backup_root)
        _run(_bench_command(payload, "set-maintenance-mode", "on"), cwd=sites_path, runner=runner)
        if settle_seconds > 0:
            time.sleep(settle_seconds)
        _stage_files(site_path, operation_id)
        staged = True
        destructive = True
        restore_state.advance(site_path, operation_id, "RESTORING")
        _run(_restore_command(payload, target), cwd=sites_path, runner=runner)
        _ensure_file_directories(site_path)
        restore_state.advance(site_path, operation_id, "MIGRATING")
        _run(_bench_command(payload, "migrate"), cwd=sites_path, runner=runner)
        _run(_bench_command(payload, "clear-cache"), cwd=sites_path, runner=runner)
        restore_state.advance(site_path, operation_id, "VERIFYING")
        _verify(payload, sites_path, runner)
        status = "Completed"
        error_code = ""
    except Exception:
        if destructive:
            restore_state.advance(site_path, operation_id, "RECOVERING")
            try:
                safety = _validate_bundle(payload["safety"], backup_root)
                _remove_restored_files(site_path)
                _run(_restore_command(payload, safety), cwd=sites_path, runner=runner)
                _ensure_file_directories(site_path)
                _run(_bench_command(payload, "migrate"), cwd=sites_path, runner=runner)
                _run(_bench_command(payload, "clear-cache"), cwd=sites_path, runner=runner)
                _verify(payload, sites_path, runner, safety=True)
                error_code = "restore_failed_safety_recovery_completed"
            except Exception:
                error_code = "restore_and_safety_recovery_failed"
        else:
            error_code = "restore_preparation_failed"

    finalize_kwargs = json.dumps(
        {
            "request_path": str(Path(request_path).resolve()),
            "status": status,
            "error_code": error_code,
        },
        separators=(",", ":"),
    )
    if error_code == "restore_and_safety_recovery_failed":
        restore_state.advance(site_path, operation_id, "MANUAL_INTERVENTION_REQUIRED")
        return 2
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
        restore_state.advance(site_path, operation_id, "MANUAL_INTERVENTION_REQUIRED")
        return 2
    try:
        if staged:
            _remove_staged_files(site_path, operation_id)
        if not payload.get("previous_maintenance"):
            _run(_bench_command(payload, "set-maintenance-mode", "off"), cwd=sites_path, runner=runner)
        restore_state.advance(site_path, operation_id,
                              "COMPLETED" if status == "Completed" else "RECOVERED_AFTER_FAILURE")
    except Exception:
        restore_state.advance(site_path, operation_id, "MANUAL_INTERVENTION_REQUIRED")
        return 2
    return 0 if status == "Completed" else 1


def _stage_files(site_path: Path, operation_id: str) -> None:
    staging = site_path / "private" / "backup_restore_requests" / f"{operation_id}-files"
    staging.mkdir(mode=0o700)
    moved: list[tuple[Path, Path]] = []
    try:
        for name, location in (("public", site_path / "public" / "files"),
                               ("private", site_path / "private" / "files")):
            if location.exists():
                destination = staging / name
                location.rename(destination)
                moved.append((location, destination))
    except Exception:
        for original, destination in reversed(moved):
            destination.rename(original)
        staging.rmdir()
        raise


def _remove_restored_files(site_path: Path) -> None:
    for path in (site_path / "public" / "files", site_path / "private" / "files"):
        if path.is_symlink():
            raise ValueError("Restored files path is a symbolic link.")
        if path.is_dir():
            shutil.rmtree(path)


def _ensure_file_directories(site_path: Path) -> None:
    for kind in ("public", "private"):
        path = site_path / kind / "files"
        if path.is_symlink():
            raise ValueError("Restored files path is a symbolic link.")
        path.mkdir(parents=True, exist_ok=True)


def _remove_staged_files(site_path: Path, operation_id: str) -> None:
    staging = site_path / "private" / "backup_restore_requests" / f"{operation_id}-files"
    if staging.exists():
        shutil.rmtree(staging)


def _verify(payload: dict[str, Any], cwd: Path, runner: Callable[..., Any], *, safety: bool = False) -> None:
    expected = "" if safety else str(payload.get("source_app_versions") or "")
    _run(_bench_command(payload, "execute",
                        "almdina_erp.almdina_erp.infrastructure.backups.restore_runner.verify_restored_site",
                        "--kwargs", json.dumps({"expected_versions": expected})), cwd=cwd, runner=runner)


def verify_restored_site(expected_versions: str = "") -> None:
    import frappe
    from almdina_erp.almdina_erp.infrastructure.backups.zip_transfer import app_versions

    frappe.db.sql("SELECT 1")
    if not frappe.db.exists("DocType", "Door Cutting Order"):
        raise ValueError("A required DocType is unavailable after restore.")
    versions = app_versions()
    if expected_versions and json.loads(expected_versions) != versions:
        raise ValueError("Application versions changed during restore.")
    if not {"frappe", "erpnext", "almdina_erp"}.issubset(versions):
        raise ValueError("Required applications are unavailable after restore.")
    site_path = Path(frappe.get_site_path()).resolve()
    for kind in ("public", "private"):
        if not (site_path / kind / "files").is_dir():
            raise ValueError("Restored files directory is unavailable.")
    for row in frappe.get_all("File", filters={"is_folder": 0}, fields=["file_url", "is_private"], limit_page_length=10):
        prefix = "/private/files/" if row.is_private else "/files/"
        url = str(row.file_url or "")
        if not url.startswith(prefix):
            continue
        root = site_path / ("private" if row.is_private else "public") / "files"
        path = (root / unquote(url[len(prefix):])).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("A restored attachment is unavailable.")


def finalize_restore(request_path: str, status: str, error_code: str = "") -> None:
    """Recreate the restore audit after the selected database is restored."""

    import frappe
    from frappe.utils import now

    from almdina_erp.almdina_erp.infrastructure.backups.history import DOCTYPE
    from almdina_erp.almdina_erp.infrastructure.backups.restore import REQUEST_FOLDER

    path = Path(request_path).resolve(strict=True)
    allowed = Path(frappe.get_site_path("private", REQUEST_FOLDER)).resolve()
    if path.parent != allowed:
        raise ValueError("Restore request is outside the site scope.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("site") != frappe.local.site:
        raise ValueError("Restore request belongs to another site.")

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
            "import_app_versions": payload.get("source_app_versions") or None,
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


__all__ = ["execute_restore", "finalize_restore"]
