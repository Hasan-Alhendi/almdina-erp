from __future__ import annotations

import fcntl
import os
import re
import time
from pathlib import Path
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now, now_datetime

from almdina_erp.almdina_erp.application.backups.management import run_backup
from almdina_erp.almdina_erp.domain.backups.policy import BackupSchedule, due_schedule_key, next_schedule_time
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import (
    FrappeBackupEngine,
    FrappeLocalRetention,
)
from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory
from almdina_erp.almdina_erp.infrastructure.backups.zip_transfer import (
    download_response, import_zip, upload_limit, validate_import_restore,
)
from almdina_erp.almdina_erp.infrastructure.backups.restore import (
    launch_restore_runner,
    preflight_restore,
    restore_runtime_ready,
    write_restore_request,
)
from almdina_erp.almdina_erp.infrastructure.backups import restore_state
from almdina_erp.almdina_erp.infrastructure.backups.sftp import (
    SFTPBackupGateway,
    SFTPGatewayError,
    SSHConfig,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    require_any_doctype_capability,
    require_doctype_capability,
)


_JOB_METHOD = "almdina_erp.almdina_erp.services.backup_restore_service.run_backup_job"
_RESTORE_JOB_METHOD = "almdina_erp.almdina_erp.services.backup_restore_service.prepare_restore_job"
_IMPORT_JOB_METHOD = "almdina_erp.almdina_erp.services.backup_restore_service.run_import_job"
_UPLOAD_CHUNK = 4 * 1024 * 1024


def _restore_site_path() -> Path:
    return Path(frappe.get_site_path()).resolve()


def _require_restore_idle() -> None:
    if restore_state.active(_restore_site_path()):
        frappe.throw(_("A restore is already in progress for this site."), frappe.ValidationError)


def _wait_for_site_jobs() -> None:
    from frappe.utils.background_jobs import get_queue, get_queue_args, get_queue_list, get_running_jobs_in_queue

    for _ in range(30):
        running = [job for queue in get_queue_list() for job in get_running_jobs_in_queue(get_queue(queue))
                   if get_queue_args(job).get("site") == frappe.local.site
                   and get_queue_args(job).get("method") != _RESTORE_JOB_METHOD]
        if not running:
            return
        time.sleep(1)
    raise ValueError("restore_jobs_busy")


def _settings() -> Any:
    return frappe.get_single("Almdina ERP Settings")


def _time(value: Any, default: str) -> str:
    if hasattr(value, "total_seconds"):
        seconds = int(value.total_seconds()) % 86400
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"
    parts = str(value or default).split(":")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except ValueError:
            pass
    return default


def _schedule(settings: Any, prefix: str) -> BackupSchedule:
    return BackupSchedule(
        frequency=settings.get(f"{prefix}_backup_frequency") or "Daily",
        time=_time(
            settings.get(f"{prefix}_backup_time"),
            "03:00" if prefix == "external" else "02:00",
        ),
        weekday=settings.get(f"{prefix}_backup_weekday") or "Monday",
        day_of_month=cint(settings.get(f"{prefix}_backup_day_of_month") or 1),
    ).validated()


def _retention(settings: Any, prefix: str) -> int:
    value = cint(settings.get(f"{prefix}_backup_retention") or (4 if prefix == "external" else 7))
    if not 1 <= value <= 365:
        raise ValueError("Backup retention must be between 1 and 365.")
    return value


def _secret(settings: Any, fieldname: str) -> str:
    return str(settings.get_password(fieldname, raise_exception=False) or "")


def _ssh_gateway(settings: Any | None = None) -> SFTPBackupGateway:
    settings = settings or _settings()
    config = SSHConfig(
        host=settings.get("ssh_host"),
        port=cint(settings.get("ssh_port") or 22),
        username=settings.get("ssh_username"),
        auth_method=settings.get("ssh_auth_method") or "Private Key",
        remote_path=settings.get("remote_backup_path"),
        site_slug=str(frappe.local.site).replace(".", "_"),
        password=_secret(settings, "ssh_password"),
        private_key=_secret(settings, "ssh_private_key"),
        private_key_passphrase=_secret(settings, "ssh_private_key_passphrase"),
    )
    try:
        return SFTPBackupGateway(config)
    except ValueError as exc:
        frappe.throw(_(str(exc)), frappe.ValidationError)
        raise AssertionError("unreachable")


def _enqueue_backup(operation_id: str, target: str) -> None:
    frappe.enqueue(
        _JOB_METHOD,
        queue="long",
        timeout=6 * 60 * 60,
        enqueue_after_commit=True,
        job_id=f"almdina-backup-{operation_id}",
        deduplicate=True,
        operation_id=operation_id,
        target=target,
    )


def _upload_path(operation_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", str(operation_id or "")):
        frappe.throw(_("Invalid backup upload."), frappe.ValidationError)
    folder = Path(frappe.get_site_path("private", "backup_zip_uploads"))
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    return folder / f"{operation_id}.zip"


def _owned_upload(operation_id: str) -> dict[str, Any]:
    row = FrappeBackupHistory().get(operation_id)
    if (not row or row.get("operation_type") != "Imported" or row.get("target") != "Local"
        or row.get("requested_by") != frappe.session.user or row.get("status") != "Queued"):
        frappe.throw(_("Backup upload is unavailable."), frappe.PermissionError)
    return row


def _cleanup_abandoned_uploads() -> None:
    folder = _upload_path("0" * 32).parent
    history = FrappeBackupHistory()
    for path in folder.glob("*.zip"):
        operation_id = path.stem
        if not re.fullmatch(r"[0-9a-f]{32}", operation_id) or path.is_symlink():
            continue
        if time.time() - path.stat().st_mtime < 24 * 60 * 60:
            continue
        row = history.get(operation_id)
        if row and row.get("operation_type") == "Imported" and row.get("status") == "Queued":
            history.mark_failed(operation_id, "upload_cancelled")
            path.unlink(missing_ok=True)


@frappe.whitelist(methods=["GET"])
def download_backup_zip(operation_id: str):
    require_doctype_capability(
        Capability.MANAGE_BACKUPS,
        message=_("You do not have permission to download backups."),
    )
    require_doctype_capability(
        Capability.RESTORE_BACKUPS,
        message=_("You do not have permission to download backups."),
    )
    try:
        return download_response(FrappeBackupHistory().resolve_local_bundle(operation_id))
    except (ValueError, OSError) as exc:
        raise frappe.ValidationError(_("Backup files are unavailable or failed integrity verification.")) from exc


@frappe.whitelist(methods=["POST"])
def begin_backup_upload(file_size: int) -> dict[str, str]:
    require_doctype_capability(Capability.MANAGE_BACKUPS)
    _require_restore_idle()
    _cleanup_abandoned_uploads()
    size = cint(file_size)
    if size <= 0 or size > upload_limit():
        frappe.throw(_("Backup ZIP exceeds the configured upload limit."), frappe.ValidationError)
    history = FrappeBackupHistory()
    operation_id = history.create(operation_type="Imported", target="Local", requested_by=frappe.session.user)
    history.set_upload_size(operation_id, size)
    path = _upload_path(operation_id)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    return {"operation_id": operation_id, "max_chunk_bytes": _UPLOAD_CHUNK}


@frappe.whitelist(methods=["POST"])
def upload_backup_chunk(operation_id: str, offset: int, file_size: int) -> dict[str, int]:
    require_doctype_capability(Capability.MANAGE_BACKUPS)
    _require_restore_idle()
    row = _owned_upload(operation_id)
    total = cint(file_size)
    position = cint(offset)
    if total <= 0 or total != int(row.get("total_size") or 0) or total > upload_limit() or position < 0 or position >= total:
        frappe.throw(_("Invalid backup upload size."), frappe.ValidationError)
    uploaded = frappe.request.files.get("file")
    if not uploaded or len(frappe.request.files) != 1:
        frappe.throw(_("Backup upload chunk is missing."), frappe.ValidationError)
    block = uploaded.stream.read(_UPLOAD_CHUNK + 1)
    if not block or len(block) > _UPLOAD_CHUNK or position + len(block) > total:
        frappe.throw(_("Invalid backup upload chunk."), frappe.ValidationError)
    with os.fdopen(os.open(_upload_path(operation_id), os.O_RDWR | os.O_NOFOLLOW), "r+b") as target:
        fcntl.flock(target, fcntl.LOCK_EX)
        if target.seek(0, os.SEEK_END) != position:
            frappe.throw(_("Backup upload chunks are out of order."), frappe.ValidationError)
        target.write(block)
    return {"received": position + len(block)}


@frappe.whitelist(methods=["POST"])
def finish_backup_upload(operation_id: str, file_size: int) -> dict[str, str]:
    require_doctype_capability(Capability.MANAGE_BACKUPS)
    _require_restore_idle()
    row = _owned_upload(operation_id)
    path = _upload_path(operation_id)
    if path.is_symlink() or path.stat().st_size != cint(file_size) or cint(file_size) != int(row.get("total_size") or 0) or path.stat().st_size > upload_limit():
        frappe.throw(_("Backup upload is incomplete."), frappe.ValidationError)
    frappe.enqueue(
        _IMPORT_JOB_METHOD, queue="long", timeout=6 * 60 * 60,
        enqueue_after_commit=True, job_id=f"almdina-import-{operation_id}", deduplicate=True,
        operation_id=operation_id,
    )
    return {"operation_id": operation_id, "status": "Queued"}


@frappe.whitelist(methods=["POST"])
def cancel_backup_upload(operation_id: str) -> None:
    require_doctype_capability(Capability.MANAGE_BACKUPS)
    _owned_upload(operation_id)
    _upload_path(operation_id).unlink(missing_ok=True)
    FrappeBackupHistory().mark_failed(operation_id, "upload_cancelled")


def run_import_job(operation_id: str) -> None:
    history = FrappeBackupHistory()
    row = history.get(operation_id)
    if not row or row.get("operation_type") != "Imported" or row.get("status") != "Queued":
        raise ValueError("Invalid import operation")
    if restore_state.active(_restore_site_path()):
        history.mark_failed(operation_id, "restore_in_progress")
        frappe.db.commit()
        _upload_path(operation_id).unlink(missing_ok=True)
        return
    source = _upload_path(operation_id)
    history.mark_running(operation_id)
    frappe.db.commit()
    try:
        import_zip(source, operation_id, history)
    except Exception as exc:
        code = str(exc) if isinstance(exc, ValueError) else "invalid_zip"
        history.mark_failed(operation_id, code if code in {
            "format", "site", "versions", "manifest", "artifacts", "size", "integrity",
            "config", "encryption_key", "database", "files", "duplicate", "upload",
        } else "invalid_zip")
        frappe.db.commit()
        raise
    finally:
        source.unlink(missing_ok=True)


@frappe.whitelist()
def get_backup_context() -> dict[str, Any]:
    require_any_doctype_capability(
        (Capability.MANAGE_BACKUPS, Capability.RESTORE_BACKUPS),
        message=_("You do not have permission to access backup management."),
    )
    can_manage = doctype_has_capability(Capability.MANAGE_BACKUPS)
    can_restore = doctype_has_capability(Capability.RESTORE_BACKUPS)
    history = FrappeBackupHistory()
    status = restore_state.public_status(_restore_site_path(), str(frappe.local.site))
    settings = _settings()
    upcoming = {}
    for prefix in ("local", "external"):
        if cint(settings.get(f"{prefix}_backup_enabled")):
            try:
                upcoming[prefix] = str(next_schedule_time(_schedule(settings, prefix), now_datetime()))
            except ValueError:
                upcoming[prefix] = ""
    latest = {}
    for target in ("Local", "External"):
        rows = frappe.get_all("Almdina Backup Operation", filters={"target": target, "status": "Completed"},
                              fields=["backup_identifier", "completed_on"], order_by="completed_on desc", limit_page_length=1)
        latest[target.lower()] = dict(rows[0]) if rows else {}
    recent = history.list_recent(30)
    return {
        "permissions": {
            "can_manage": can_manage,
            "can_restore": can_restore,
            "can_download": can_manage and can_restore,
        },
        "history": recent,
        "backup_running": any(row.get("operation_type") in ("Manual", "Scheduled") and
                              row.get("status") in ("Queued", "Running") for row in recent),
        "restorable": history.restorable(30) if can_restore else [],
        "upload_max_bytes": upload_limit() if can_manage else 0,
        "restore_runtime_ready": bool(can_restore and restore_runtime_ready()),
        "restore_status": status if can_restore else {},
        "site": str(frappe.local.site),
        "upcoming": upcoming,
        "latest": latest,
    }


@frappe.whitelist()
def create_backup_now() -> dict[str, str]:
    require_doctype_capability(
        Capability.MANAGE_BACKUPS,
        message=_("You do not have permission to create backups."),
    )
    _require_restore_idle()
    if frappe.db.exists("Almdina Backup Operation", {
        "target": "Local", "operation_type": ["in", ["Manual", "Scheduled"]],
        "status": ["in", ["Queued", "Running"]],
    }):
        frappe.throw(_("A local backup is already in progress."), frappe.ValidationError)
    history = FrappeBackupHistory()
    operation_id = history.create(
        operation_type="Manual",
        target="Local",
        requested_by=frappe.session.user,
    )
    _enqueue_backup(operation_id, "local")
    return {"operation_id": operation_id, "status": "Queued"}


@frappe.whitelist()
def test_ssh_connection() -> dict[str, bool]:
    require_doctype_capability(
        Capability.MANAGE_BACKUPS,
        message=_("You do not have permission to test backup connections."),
    )
    try:
        _ssh_gateway().test_connection()
    except SFTPGatewayError as exc:
        messages = {
            "ssh_authentication_failed": _("SSH authentication failed. Check the configured credentials."),
            "ssh_connection_failed": _("Could not reach the backup server. Check the address and network."),
            "ssh_remote_path_invalid": _("The remote backup directory is unavailable or not writable."),
        }
        frappe.throw(messages.get(exc.safe_code, _("SSH connection test failed.")), frappe.ValidationError)
    return {"ok": True}


@frappe.whitelist()
def request_restore(operation_id: str, confirmation: str) -> dict[str, str]:
    require_doctype_capability(
        Capability.RESTORE_BACKUPS,
        message=_("You do not have permission to restore backups."),
    )
    if not restore_runtime_ready():
        frappe.throw(
            _("Restore requires the database root password in Frappe site/common configuration."),
            frappe.ValidationError,
        )
    history = FrappeBackupHistory()
    bundle = history.resolve_local_bundle(operation_id)
    source_row = history.get(str(operation_id or "").strip())
    if source_row and (source_row.get("operation_type") == "Imported" or source_row.get("import_app_versions")):
        try:
            validate_import_restore(source_row.get("import_app_versions") or "", bundle)
        except (ValueError, OSError) as exc:
            raise frappe.ValidationError(_("Selected backup is no longer compatible with this site.")) from exc
    expected = f"RESTORE {bundle.identifier}"
    if str(confirmation or "").strip() != expected:
        frappe.throw(_("Restore confirmation does not match the selected backup."), frappe.ValidationError)
    if frappe.db.count("Almdina Backup Operation", {
        "status": ["in", ["Running", "Prepared"]],
        "operation_type": ["in", ["Manual", "Scheduled", "Imported", "Restore"]],
    }):
        frappe.throw(_("Wait for the current backup or import to finish before restoring."), frappe.ValidationError)
    try:
        preflight_restore(bundle)
    except Exception as exc:
        code = str(exc) if isinstance(exc, ValueError) else "restore_preflight_unavailable"
        messages = {
            "restore_runtime_not_configured": _("Restore needs database administrator credentials in the operational configuration."),
            "restore_db_admin_unavailable": _("Database administrator access is unavailable. Check the operational configuration."),
            "restore_db_unavailable": _("The site database is unavailable. Restore has not started."),
            "restore_disk_space": _("There is insufficient free disk space for a safety backup and restore."),
            "restore_tools_unavailable": _("The restore tools are unavailable on this server."),
        }
        raise frappe.ValidationError(messages.get(code, _("Restore preflight failed. Please contact the administrator."))) from exc
    restore_id = history.create(
        operation_type="Restore",
        target="Restore",
        requested_by=frappe.session.user,
        source_operation_id=str(operation_id or "").strip(),
    )
    try:
        restore_state.claim(_restore_site_path(), str(frappe.local.site), restore_id)
        frappe.enqueue(
            _RESTORE_JOB_METHOD,
            queue="long",
            timeout=6 * 60 * 60,
            enqueue_after_commit=True,
            job_id=f"almdina-restore-prepare-{restore_id}",
            deduplicate=True,
            operation_id=restore_id,
        )
    except ValueError as exc:
        raise frappe.ValidationError(_("A restore is already in progress for this site.")) from exc
    except Exception:
        restore_state.advance(_restore_site_path(), restore_id, "MANUAL_INTERVENTION_REQUIRED")
        raise
    return {"operation_id": restore_id, "status": "Queued"}


def scheduled_backup_tick() -> None:
    """Minute-level scheduler hook; it only enqueues due long-running jobs."""

    if restore_state.active(_restore_site_path()):
        return
    settings = _settings()
    current = now_datetime()
    history = FrappeBackupHistory()
    for prefix, target in (("local", "Local"), ("external", "External")):
        if not cint(settings.get(f"{prefix}_backup_enabled")):
            continue
        try:
            schedule_key = due_schedule_key(prefix, _schedule(settings, prefix), current)
        except ValueError:
            frappe.logger("almdina_backup").error("Invalid %s backup schedule", prefix)
            continue
        if not schedule_key or history.exists_for_schedule(schedule_key):
            continue
        try:
            operation_id = history.create(
                operation_type="Scheduled",
                target=target,
                requested_by="Administrator",
                schedule_key=schedule_key,
            )
        except Exception:
            if history.exists_for_schedule(schedule_key):
                continue
            raise
        _enqueue_backup(operation_id, prefix)


def run_backup_job(operation_id: str, target: str) -> None:
    history = FrappeBackupHistory()
    row = history.get(operation_id)
    normalized = str(target or "").strip().lower()
    expected_target = "External" if normalized == "external" else "Local"
    if not row or row.get("status") != "Queued" or row.get("target") != expected_target:
        raise ValueError("Backup job operation is invalid.")
    if restore_state.active(_restore_site_path()):
        history.mark_failed(operation_id, "restore_in_progress")
        frappe.db.commit()
        return
    settings = _settings()
    try:
        if normalized == "external":
            if row.get("operation_type") == "Scheduled" and not cint(settings.get("external_backup_enabled")):
                raise ValueError("External backup is disabled.")
            run_backup(
                operation_id=operation_id,
                target="external",
                engine=FrappeBackupEngine(ephemeral=True),
                history=history,
                keep_last=_retention(settings, "external"),
                external=_ssh_gateway(settings),
            )
        elif normalized == "local":
            if row.get("operation_type") == "Scheduled" and not cint(settings.get("local_backup_enabled")):
                raise ValueError("Local backup is disabled.")
            run_backup(
                operation_id=operation_id,
                target="local",
                engine=FrappeBackupEngine(),
                history=history,
                keep_last=_retention(settings, "local"),
                local_retention=FrappeLocalRetention(),
            )
        else:
            raise ValueError("Backup target is invalid.")
        frappe.db.commit()
    except Exception:
        frappe.db.commit()
        raise


def prepare_restore_job(operation_id: str) -> None:
    history = FrappeBackupHistory()
    restore_row = history.get(operation_id)
    if not restore_row or restore_row.get("operation_type") != "Restore" or restore_row.get("status") != "Queued":
        raise ValueError("Restore operation is invalid.")
    if restore_state.read(_restore_site_path()).get("operation_id") != operation_id:
        raise ValueError("Restore claim is invalid.")
    restore_state.advance(_restore_site_path(), operation_id, "PREFLIGHT", runner_pid=os.getpid())
    if not restore_runtime_ready():
        history.mark_failed(operation_id, "restore_runtime_not_configured")
        frappe.db.commit()
        restore_state.advance(_restore_site_path(), operation_id, "RECOVERED_AFTER_FAILURE")
        return

    history.mark_running(operation_id)
    source_operation_id = str(restore_row.get("source_operation_id") or "")
    previous_maintenance = bool(frappe.conf.get("maintenance_mode"))
    maintenance_enabled = False
    safety_operation_id = ""
    safety_completed = False
    try:
        source_row = history.get(source_operation_id)
        if not source_row:
            raise ValueError("Restore source operation is unavailable.")
        target = history.resolve_local_bundle(source_operation_id)
        if source_row.get("operation_type") == "Imported" or source_row.get("import_app_versions"):
            validate_import_restore(source_row.get("import_app_versions") or "", target)
        preflight_restore(target)
        from frappe.installer import update_site_config

        if not previous_maintenance:
            update_site_config("maintenance_mode", 1)
            maintenance_enabled = True
        _wait_for_site_jobs()

        safety_operation_id = history.create(
            operation_type="Safety",
            target="Local",
            requested_by=restore_row.get("requested_by") or "Administrator",
        )
        history.mark_running(safety_operation_id)
        restore_state.advance(_restore_site_path(), operation_id, "SAFETY_BACKUP")
        safety_engine = FrappeBackupEngine()
        safety = safety_engine.create()
        history.mark_completed(safety_operation_id, safety, safety.identifier)
        safety_completed = True

        request_path = write_restore_request(
            operation_id=operation_id,
            source_operation_id=source_operation_id,
            source_operation_type=source_row.get("operation_type") or "Manual",
            source_app_versions=source_row.get("import_app_versions") or "",
            source_requested_by=source_row.get("requested_by") or "Administrator",
            source_requested_on=str(source_row.get("requested_on") or now()),
            source_completed_on=str(source_row.get("completed_on") or source_row.get("requested_on") or now()),
            requested_by=restore_row.get("requested_by") or "Administrator",
            requested_on=str(restore_row.get("requested_on") or now()),
            target=target,
            safety_operation_id=safety_operation_id,
            safety=safety,
            previous_maintenance=previous_maintenance,
        )
        history.mark_restore_prepared(
            operation_id,
            source_operation_id=source_operation_id,
            backup_identifier=target.identifier,
            safety_operation_id=safety_operation_id,
        )
        frappe.db.commit()
        restore_state.advance(_restore_site_path(), operation_id, "SAFETY_BACKUP", runner_pid=0)
        launch_restore_runner(request_path)
    except Exception as exc:
        if safety_operation_id and not safety_completed:
            history.mark_failed(safety_operation_id, "safety_backup_failed")
        history.mark_failed(operation_id, getattr(exc, "safe_code", exc.__class__.__name__))
        frappe.db.commit()
        try:
            if maintenance_enabled:
                update_site_config("maintenance_mode", 0)
            restore_state.advance(_restore_site_path(), operation_id, "RECOVERED_AFTER_FAILURE")
        except Exception:
            restore_state.advance(_restore_site_path(), operation_id, "MANUAL_INTERVENTION_REQUIRED")
        raise


__all__ = [
    "create_backup_now",
    "get_backup_context",
    "prepare_restore_job",
    "request_restore",
    "run_backup_job",
    "scheduled_backup_tick",
    "test_ssh_connection",
]
