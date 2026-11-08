from __future__ import annotations

from pathlib import Path
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now, now_datetime

from almdina_erp.almdina_erp.application.backups.delete_backup import (
    BackupDeleteError,
    delete_backup_operation as run_delete_backup_operation,
)
from almdina_erp.almdina_erp.application.backups.import_backup import import_backup_zip as run_import_backup_zip
from almdina_erp.almdina_erp.application.backups.management import BackupBundle, run_backup
from almdina_erp.almdina_erp.infrastructure.backups.delete_backup import FrappeBackupDeleteGateway
from almdina_erp.almdina_erp.domain.backups.policy import BackupSchedule, due_schedule_key
from almdina_erp.almdina_erp.domain.backups.retry import (
    MAX_BACKUP_ATTEMPTS,
    decide_external_backup_retry,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.backups.db_root import (
    DbRootAuthenticationError,
    DbRootConnectionError,
    DbRootHostUnreachable,
    DbRootInsufficientPrivileges,
    DbRootSettingsIncomplete,
    public_db_root_settings,
    resolve_effective_db_root,
    restore_runtime_ready,
    test_db_root_connection,
)
from almdina_erp.almdina_erp.domain.backups.encryption import validate_age_public_key
from almdina_erp.almdina_erp.infrastructure.backups.age_crypto import BackupEncryptionError
from almdina_erp.almdina_erp.infrastructure.backups.encrypted_external import AgeEncryptedExternalGateway
from almdina_erp.almdina_erp.infrastructure.backups.export_zip import (
    BackupExportError,
    annotate_downloadable,
    build_backup_zip_export,
    cleanup_export_paths,
    send_backup_zip_response,
)
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import (
    FrappeBackupEngine,
    FrappeLocalRetention,
)
from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory
from almdina_erp.almdina_erp.infrastructure.backups.import_zip import (
    BackupImportError,
    LocalBackupZipImporter,
)
from almdina_erp.almdina_erp.infrastructure.backups.restore import (
    assert_restore_preflight,
    launch_restore_runner,
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


def _external_backup_gateway(settings: Any | None = None) -> AgeEncryptedExternalGateway:
    """SFTP upload wrapped with age encryption; private keys never enter this path."""

    settings = settings or _settings()
    try:
        public_key = validate_age_public_key(settings.get("external_backup_age_public_key"))
    except ValueError as exc:
        raise BackupEncryptionError(str(exc) or "backup_encryption_public_key_missing") from exc
    return AgeEncryptedExternalGateway(_ssh_gateway(settings), public_key=public_key)


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


class _DeferredFailureHistory:
    """Capture failure codes without marking Failed so External retries can be scheduled."""

    def __init__(self, history: FrappeBackupHistory) -> None:
        self._history = history
        self.failure_code: str | None = None

    def mark_running(self, operation_id: str) -> None:
        # begin_attempt already transitioned Queued -> Running for External retries.
        return None

    def mark_completed(self, operation_id: str, bundle: BackupBundle, reference: str = "") -> None:
        self._history.mark_completed(operation_id, bundle, reference)

    def mark_failed(self, operation_id: str, error_code: str) -> None:
        self.failure_code = str(error_code or "backup_operation_failed")[:140]


def _enqueue_due_external_retries(history: FrappeBackupHistory, *, current) -> None:
    for row in history.due_external_retries(now=current):
        operation_id = str(row.get("operation_id") or "").strip()
        if not operation_id:
            continue
        try:
            _enqueue_backup(operation_id, "external")
            frappe.db.commit()
        except Exception:
            frappe.logger("almdina_backup").error(
                "Failed to enqueue deferred external backup retry for %s",
                operation_id,
                exc_info=True,
            )


def _safe_db_root_error_message(exc: Exception) -> str:
    if isinstance(exc, DbRootSettingsIncomplete):
        return _("Database restore settings are incomplete.")
    if isinstance(exc, DbRootAuthenticationError):
        return _("Database authentication failed. Check the root username and password.")
    if isinstance(exc, DbRootHostUnreachable):
        return _("Could not reach the database host or port.")
    if isinstance(exc, DbRootInsufficientPrivileges):
        return _("Connected successfully, but the account lacks restore privileges.")
    if isinstance(exc, DbRootConnectionError):
        return _("Database connection test failed.")
    return _("Database connection test failed.")


def _safe_export_error_message(exc: BackupExportError) -> str:
    code = str(exc.safe_code or "")
    if code == "backup_export_not_found":
        return _("Backup was not found.")
    if code == "backup_export_not_eligible":
        return _("This backup cannot be downloaded.")
    if code in {
        "backup_export_missing_component",
        "backup_export_incomplete_components",
        "backup_export_integrity_failed",
        "backup_export_invalid_manifest",
    }:
        return _("Backup files are incomplete or failed integrity checks.")
    if code in {"backup_export_external_unavailable", "ssh_download_failed", "ssh_connection_failed", "ssh_authentication_failed", "ssh_remote_path_invalid"}:
        return _("Could not fetch the external backup for download.")
    if code == "backup_export_encrypted_requires_offline_decrypt":
        return _(
            "This external backup is encrypted. Download a plaintext ZIP is not available on the server; decrypt the remote .age files offline with the private key, then build an Import-compatible ZIP."
        )
    return _("Could not prepare the backup download.")


@frappe.whitelist()
def get_backup_context() -> dict[str, Any]:
    require_any_doctype_capability(
        (Capability.MANAGE_BACKUPS, Capability.RESTORE_BACKUPS),
        message=_("You do not have permission to access backup management."),
    )
    can_manage = doctype_has_capability(Capability.MANAGE_BACKUPS)
    can_manage_db_restore = doctype_has_capability(Capability.MANAGE_DB_RESTORE_SETTINGS)
    can_restore = doctype_has_capability(Capability.RESTORE_BACKUPS)
    history = FrappeBackupHistory()
    ready = bool(restore_runtime_ready())
    rows = history.list_recent(30)
    payload: dict[str, Any] = {
        "permissions": {
            "can_manage": can_manage,
            "can_manage_db_restore_settings": can_manage_db_restore,
            "can_restore": can_restore,
        },
        "history": annotate_downloadable(rows) if can_manage else rows,
        "restorable": history.restorable(30) if can_restore else [],
        "restore_runtime_ready": bool(can_restore and ready),
    }
    if can_manage_db_restore:
        payload["db_root"] = public_db_root_settings()
    return payload


@frappe.whitelist()
def download_backup_zip(operation_id: str):
    """Stream a unified ZIP export for one completed backup operation."""

    require_doctype_capability(
        Capability.MANAGE_BACKUPS,
        message=_("You do not have permission to download backups."),
    )
    packed = None
    try:
        packed = build_backup_zip_export(
            str(operation_id or "").strip(),
            sftp_factory=_ssh_gateway,
        )
        return send_backup_zip_response(packed)
    except BackupExportError as exc:
        if packed is not None:
            cleanup_export_paths(packed.cleanup_paths)
        frappe.throw(_safe_export_error_message(exc), frappe.ValidationError)
    except Exception:
        if packed is not None:
            cleanup_export_paths(packed.cleanup_paths)
        frappe.throw(_("Could not prepare the backup download."), frappe.ValidationError)


def _safe_import_error_message(exc: BackupImportError) -> str:
    code = str(exc.safe_code or "")
    mapping = {
        "backup_import_unsupported_format": _("This backup package format is not supported."),
        "backup_import_invalid_manifest": _("The backup package manifest is invalid."),
        "backup_import_missing_manifest": _("The backup package is missing manifest.json."),
        "backup_import_incomplete_components": _("The backup package is missing required components."),
        "backup_import_integrity_failed": _("Backup package files failed integrity checks."),
        "backup_import_corrupt_zip": _("The uploaded file is not a valid ZIP archive."),
        "backup_import_encrypted": _("Encrypted backup packages are not supported."),
        "backup_import_zip_bomb": _("The backup package failed safe-size validation."),
        "backup_import_unsafe_path": _("The backup package contains unsafe file paths."),
        "backup_import_duplicate_member": _("The backup package contains duplicate members."),
        "backup_import_unexpected_members": _("The backup package contains unexpected files."),
        "backup_import_site_mismatch": _("This backup package belongs to a different site."),
        "backup_import_database_type_mismatch": _("This backup package does not match the current database type."),
        "backup_import_identifier_mismatch": _("Backup package identifiers do not match the component filenames."),
        "backup_import_duplicate": _("A backup with these files already exists on this site."),
        "backup_import_missing_file": _("The uploaded backup file was not found."),
        "backup_import_history_failed": _("Could not register the imported backup."),
    }
    return mapping.get(code, _("Could not import the backup package."))


def _resolve_private_upload_path(file_url: str, file_id: str | None = None) -> tuple[str, str]:
    """Return (file_name, absolute_path) for a private unattached staging upload."""

    normalized_url = str(file_url or "").strip()
    if not normalized_url.startswith("/private/files/") or ".." in normalized_url:
        frappe.throw(_("The uploaded backup file was not found."), frappe.ValidationError)
    if not normalized_url.lower().split("?", 1)[0].endswith(".zip"):
        frappe.throw(_("Please upload a ZIP backup package."), frappe.ValidationError)

    fields = ["name", "file_url", "is_private", "attached_to_doctype", "attached_to_name", "owner"]
    file_row = None
    if file_id:
        file_row = frappe.db.get_value(
            "File",
            {"name": str(file_id).strip(), "file_url": normalized_url},
            fields,
            as_dict=True,
        )
    if file_row is None:
        file_row = frappe.db.get_value(
            "File",
            {
                "file_url": normalized_url,
                "owner": frappe.session.user,
                "is_private": 1,
                "attached_to_doctype": ["is", "not set"],
                "attached_to_name": ["is", "not set"],
            },
            fields,
            as_dict=True,
        )
    if not file_row or not cint(file_row.is_private):
        frappe.throw(_("The uploaded backup file was not found."), frappe.ValidationError)
    if file_row.attached_to_doctype or file_row.attached_to_name:
        frappe.throw(_("The uploaded backup file was not found."), frappe.ValidationError)
    if str(file_row.owner or "") != str(frappe.session.user) and frappe.session.user != "Administrator":
        frappe.throw(_("The uploaded backup file was not found."), frappe.ValidationError)

    relative = normalized_url.lstrip("/")
    absolute = Path(frappe.get_site_path(relative)).resolve()
    private_files = Path(frappe.get_site_path("private", "files")).resolve()
    try:
        absolute.relative_to(private_files)
    except ValueError as exc:
        raise frappe.ValidationError(_("The uploaded backup file was not found.")) from exc
    if not absolute.is_file() or absolute.is_symlink():
        frappe.throw(_("The uploaded backup file was not found."), frappe.ValidationError)
    return str(file_row.name), str(absolute)


def _delete_staging_file(file_name: str) -> None:
    try:
        if file_name and frappe.db.exists("File", file_name):
            frappe.delete_doc("File", file_name, ignore_permissions=True, delete_permanently=True)
    except Exception:
        frappe.logger("almdina_backup").error("Failed deleting backup import staging file", exc_info=True)


@frappe.whitelist()
def import_backup_zip(file_url: str, file_id: str | None = None) -> dict[str, Any]:
    """Import one Almdina backup ZIP into the local backup store."""

    require_doctype_capability(
        Capability.MANAGE_BACKUPS,
        message=_("You do not have permission to import backups."),
    )
    file_name, absolute = _resolve_private_upload_path(file_url, file_id)
    try:
        result = run_import_backup_zip(
            zip_path=absolute,
            gateway=LocalBackupZipImporter(),
            site=str(frappe.local.site),
            site_slug=str(frappe.local.site).replace(".", "_"),
            database_type=str(getattr(frappe.conf, "db_type", None) or "mariadb"),
            requested_by=frappe.session.user,
        )
    except BackupImportError as exc:
        _delete_staging_file(file_name)
        frappe.throw(_safe_import_error_message(exc), frappe.ValidationError)
    except Exception:
        _delete_staging_file(file_name)
        frappe.throw(_("Could not import the backup package."), frappe.ValidationError)
    _delete_staging_file(file_name)
    return {
        "operation_id": result.operation_id,
        "backup_identifier": result.backup_identifier,
        "total_size": result.total_size,
        "status": "Completed",
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
    try:
        _enqueue_backup(operation_id, "local")
    except Exception:
        history.mark_failed(operation_id, "backup_enqueue_failed")
        frappe.db.commit()
        frappe.throw(_("Could not queue the backup job."), frappe.ValidationError)
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
def test_db_connection() -> dict[str, Any]:
    require_doctype_capability(
        Capability.MANAGE_DB_RESTORE_SETTINGS,
        message=_("You do not have permission to manage database restore settings."),
    )
    try:
        result = test_db_root_connection(resolve_effective_db_root())
    except DbRootConnectionError as exc:
        frappe.throw(_safe_db_root_error_message(exc), frappe.ValidationError)
    except ValueError:
        frappe.throw(_("Database restore settings are incomplete."), frappe.ValidationError)
    return {
        "ok": True,
        "authenticated": bool(result.get("authenticated")),
        "has_restore_privileges": bool(result.get("has_restore_privileges")),
        "source": str(result.get("source") or ""),
        "safe_code": str(result.get("safe_code") or "db_root_connection_ok"),
    }


def _safe_delete_error_message(exc: BackupDeleteError) -> str:
    code = str(exc.safe_code or "")
    mapping = {
        "backup_delete_missing_operation": _("Backup was not found."),
        "backup_delete_not_found": _("Backup was not found."),
        "backup_delete_not_eligible": _("This backup cannot be deleted."),
        "backup_delete_restore_protected": _("This backup is protected by an active restore and cannot be deleted."),
        "backup_delete_operation_busy": _("This backup is busy with another backup or download and cannot be deleted."),
        "backup_delete_unsafe_path": _("Backup files are outside the approved backup scope."),
        "backup_delete_symlink_rejected": _("Backup files failed safety checks."),
        "backup_delete_integrity_failed": _("Backup files failed integrity checks."),
        "backup_delete_files_failed": _("Could not delete backup files."),
        "backup_delete_record_failed": _("Could not delete the backup history record."),
        "backup_delete_record_failed_after_files": _(
            "Backup files were removed but the history record could not be deleted. Contact an administrator."
        ),
    }
    return mapping.get(code, _("Could not delete the backup."))


@frappe.whitelist()
def delete_backup(operation_id: str) -> dict[str, object]:
    """Delete one backup operation (Completed, or Failed delete-orphan retry). External: history only."""

    require_doctype_capability(
        Capability.MANAGE_BACKUPS,
        message=_("You do not have permission to delete backups."),
    )
    try:
        result = run_delete_backup_operation(
            operation_id=str(operation_id or "").strip(),
            gateway=FrappeBackupDeleteGateway(),
        )
    except BackupDeleteError as exc:
        frappe.throw(_safe_delete_error_message(exc), frappe.ValidationError)
    except Exception:
        frappe.throw(_("Could not delete the backup."), frappe.ValidationError)

    if result.outcome == "record_only_external":
        message = _(
            "Backup history was deleted. Remote external files were not removed from the SFTP server."
        )
    elif result.outcome == "record_only_shared_refs":
        message = _(
            "Backup history was deleted. Files were kept because another backup still references them."
        )
    elif result.outcome == "record_only_orphan_cleanup":
        message = _("Orphaned backup history was deleted after files were already removed.")
    else:
        message = _("Backup files and history were deleted.")

    return {
        "operation_id": result.operation_id,
        "backup_identifier": result.backup_identifier,
        "target": result.target,
        "operation_type": result.operation_type,
        "files_deleted": bool(result.files_deleted),
        "record_deleted": bool(result.record_deleted),
        "remote_files_deleted": bool(result.remote_files_deleted),
        "outcome": result.outcome,
        "message": message,
    }


@frappe.whitelist()
def request_restore(operation_id: str, confirmation: str) -> dict[str, str]:
    require_doctype_capability(
        Capability.RESTORE_BACKUPS,
        message=_("You do not have permission to restore backups."),
    )
    if not restore_runtime_ready():
        frappe.throw(
            _("Restore requires complete database root connection settings."),
            frappe.ValidationError,
        )
    history = FrappeBackupHistory()
    if history.has_active_restore():
        frappe.throw(
            _("A restore operation is already in progress on this site."),
            frappe.ValidationError,
        )
    # Local restorable types only (Manual/Scheduled/Safety/Imported). External is rejected.
    bundle = history.resolve_local_bundle(operation_id)
    try:
        assert_restore_preflight(required_bytes=int(bundle.total_size or 0))
    except ValueError as exc:
        code = str(exc)
        if code == "restore_insufficient_disk_space":
            frappe.throw(
                _("Not enough free disk space to create the safety backup before restore."),
                frappe.ValidationError,
            )
        frappe.throw(
            _("Restore requires complete database root connection settings."),
            frappe.ValidationError,
        )
    expected = f"RESTORE {bundle.identifier}"
    if str(confirmation or "").strip() != expected:
        frappe.throw(_("Restore confirmation does not match the selected backup."), frappe.ValidationError)
    restore_id = history.create(
        operation_type="Restore",
        target="Restore",
        requested_by=frappe.session.user,
        source_operation_id=str(operation_id or "").strip(),
    )
    try:
        frappe.enqueue(
            _RESTORE_JOB_METHOD,
            queue="long",
            timeout=6 * 60 * 60,
            enqueue_after_commit=True,
            job_id=f"almdina-restore-prepare-{restore_id}",
            deduplicate=True,
            operation_id=restore_id,
        )
    except Exception:
        history.mark_failed(restore_id, "restore_enqueue_failed")
        frappe.db.commit()
        frappe.throw(_("Could not queue the restore preparation job."), frappe.ValidationError)
    return {"operation_id": restore_id, "status": "Queued"}


def scheduled_backup_tick() -> None:
    """Minute-level scheduler hook; it only enqueues due long-running jobs."""

    settings = _settings()
    current = now_datetime()
    history = FrappeBackupHistory()
    try:
        history.reclaim_stale_operations(now=current)
        frappe.db.commit()
    except Exception:
        frappe.logger("almdina_backup").error("Failed reclaiming stale backup operations", exc_info=True)

    _enqueue_due_external_retries(history, current=current)

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
        try:
            _enqueue_backup(operation_id, prefix)
            frappe.db.commit()
        except Exception:
            history.mark_failed(operation_id, "backup_enqueue_failed")
            frappe.db.commit()
            frappe.logger("almdina_backup").error(
                "Failed to enqueue scheduled %s backup",
                prefix,
                exc_info=True,
            )


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
                history.mark_failed(operation_id, "external_backup_disabled")
                frappe.db.commit()
                raise ValueError("External backup is disabled.")
            next_retry_on = get_datetime(row.get("next_retry_on")) if row.get("next_retry_on") else None
            if next_retry_on and next_retry_on > now_datetime():
                return
            attempt = cint(row.get("attempt_count") or 0) + 1
            if attempt > MAX_BACKUP_ATTEMPTS:
                history.mark_failed(
                    operation_id,
                    "backup_retry_exhausted",
                    attempt=cint(row.get("attempt_count") or 0),
                )
                frappe.db.commit()
                return
            history.begin_attempt(operation_id, attempt)
            deferred = _DeferredFailureHistory(history)
            try:
                run_backup(
                    operation_id=operation_id,
                    target="external",
                    engine=FrappeBackupEngine(ephemeral=True),
                    history=deferred,
                    keep_last=_retention(settings, "external"),
                    external=_external_backup_gateway(settings),
                )
            except Exception as exc:
                code = deferred.failure_code or str(getattr(exc, "safe_code", None) or exc.__class__.__name__)[:140]
                decision = decide_external_backup_retry(attempt=attempt, error_code=code)
                if decision.action == "retry" and decision.delay_seconds is not None:
                    history.schedule_retry(
                        operation_id,
                        attempt=attempt,
                        error_code=decision.error_code,
                        delay_seconds=decision.delay_seconds,
                    )
                    frappe.db.commit()
                    return
                history.mark_failed(operation_id, decision.error_code, attempt=attempt)
                frappe.db.commit()
                raise
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
        if str(source_row.get("target") or "") != "Local":
            history.mark_failed(operation_id, "restore_external_not_supported")
            frappe.db.commit()
            return
        target = history.resolve_local_bundle(source_operation_id)
        assert_restore_preflight(required_bytes=int(target.total_size or 0))

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
    "delete_backup",
    "download_backup_zip",
    "get_backup_context",
    "import_backup_zip",
    "prepare_restore_job",
    "request_restore",
    "run_backup_job",
    "scheduled_backup_tick",
    "test_db_connection",
    "test_ssh_connection",
]
