from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now, now_datetime

from almdina_erp.almdina_erp.application.backups.management import run_backup
from almdina_erp.almdina_erp.domain.backups.policy import BackupSchedule, due_schedule_key
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import (
    FrappeBackupEngine,
    FrappeLocalRetention,
)
from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory
from almdina_erp.almdina_erp.infrastructure.backups.restore import (
    launch_restore_runner,
    restore_runtime_ready,
    write_restore_request,
)
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


@frappe.whitelist()
def get_backup_context() -> dict[str, Any]:
    require_any_doctype_capability(
        (Capability.MANAGE_BACKUPS, Capability.RESTORE_BACKUPS),
        message=_("You do not have permission to access backup management."),
    )
    can_manage = doctype_has_capability(Capability.MANAGE_BACKUPS)
    can_restore = doctype_has_capability(Capability.RESTORE_BACKUPS)
    history = FrappeBackupHistory()
    return {
        "permissions": {
            "can_manage": can_manage,
            "can_restore": can_restore,
        },
        "history": history.list_recent(30),
        "restorable": history.restorable(30) if can_restore else [],
        "restore_runtime_ready": bool(can_restore and restore_runtime_ready()),
    }


@frappe.whitelist()
def create_backup_now() -> dict[str, str]:
    require_doctype_capability(
        Capability.MANAGE_BACKUPS,
        message=_("You do not have permission to create backups."),
    )
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
        frappe.throw(_("SSH connection test failed ({0}).").format(exc.safe_code), frappe.ValidationError)
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
    expected = f"RESTORE {bundle.identifier}"
    if str(confirmation or "").strip() != expected:
        frappe.throw(_("Restore confirmation does not match the selected backup."), frappe.ValidationError)
    restore_id = history.create(
        operation_type="Restore",
        target="Restore",
        requested_by=frappe.session.user,
        source_operation_id=str(operation_id or "").strip(),
    )
    frappe.enqueue(
        _RESTORE_JOB_METHOD,
        queue="long",
        timeout=6 * 60 * 60,
        enqueue_after_commit=True,
        job_id=f"almdina-restore-prepare-{restore_id}",
        deduplicate=True,
        operation_id=restore_id,
    )
    return {"operation_id": restore_id, "status": "Queued"}


def scheduled_backup_tick() -> None:
    """Minute-level scheduler hook; it only enqueues due long-running jobs."""

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
    if not restore_runtime_ready():
        history.mark_failed(operation_id, "restore_runtime_not_configured")
        frappe.db.commit()
        return

    history.mark_running(operation_id)
    source_operation_id = str(restore_row.get("source_operation_id") or "")
    try:
        source_row = history.get(source_operation_id)
        if not source_row:
            raise ValueError("Restore source operation is unavailable.")
        target = history.resolve_local_bundle(source_operation_id)

        safety_operation_id = history.create(
            operation_type="Safety",
            target="Local",
            requested_by=restore_row.get("requested_by") or "Administrator",
        )
        history.mark_running(safety_operation_id)
        safety_engine = FrappeBackupEngine()
        safety = safety_engine.create()
        history.mark_completed(safety_operation_id, safety, safety.identifier)

        request_path = write_restore_request(
            operation_id=operation_id,
            source_operation_id=source_operation_id,
            source_operation_type=source_row.get("operation_type") or "Manual",
            source_requested_by=source_row.get("requested_by") or "Administrator",
            source_requested_on=str(source_row.get("requested_on") or now()),
            source_completed_on=str(source_row.get("completed_on") or source_row.get("requested_on") or now()),
            requested_by=restore_row.get("requested_by") or "Administrator",
            requested_on=str(restore_row.get("requested_on") or now()),
            target=target,
            safety_operation_id=safety_operation_id,
            safety=safety,
        )
        history.mark_restore_prepared(
            operation_id,
            source_operation_id=source_operation_id,
            backup_identifier=target.identifier,
            safety_operation_id=safety_operation_id,
        )
        frappe.db.commit()
        launch_restore_runner(request_path)
    except Exception as exc:
        history.mark_failed(operation_id, getattr(exc, "safe_code", exc.__class__.__name__))
        frappe.db.commit()
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
