"""Delete one backup operation (framework-free use case)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from almdina_erp.almdina_erp.application.backups.management import BackupBundle


DELETABLE_LOCAL_OPERATION_TYPES = frozenset({"Manual", "Scheduled", "Safety", "Imported"})
DELETABLE_EXTERNAL_OPERATION_TYPES = frozenset({"Manual", "Scheduled"})
# Only these Failed markers may use orphan record-only cleanup / resume delete.
DELETE_ORPHAN_ERROR_CODES = frozenset(
    {
        "backup_delete_pending",
        "backup_delete_files_failed",
        "backup_delete_record_failed_after_files",
    }
)


class BackupDeleteError(ValueError):
    """Safe, stable delete failure code for service mapping."""

    def __init__(self, safe_code: str) -> None:
        code = str(safe_code or "backup_delete_failed")[:140]
        self.safe_code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DeletableBackupOperation:
    operation_id: str
    operation_type: str
    target: str
    status: str
    backup_identifier: str
    error_summary: str = ""


@dataclass(frozen=True, slots=True)
class BackupDeleteResult:
    operation_id: str
    backup_identifier: str
    target: str
    operation_type: str
    files_deleted: bool
    record_deleted: bool
    remote_files_deleted: bool
    outcome: str


class BackupDeleteGateway(Protocol):
    def load_operation(self, operation_id: str) -> DeletableBackupOperation: ...

    def count_other_local_references(
        self,
        backup_identifier: str,
        *,
        exclude_operation_id: str,
    ) -> int: ...

    def is_protected_by_active_restore(
        self,
        *,
        operation_id: str,
        backup_identifier: str,
    ) -> bool: ...

    def is_backup_or_export_busy(
        self,
        *,
        operation_id: str,
        backup_identifier: str,
    ) -> bool: ...

    def prepare_local_delete_bundle(self, operation_id: str) -> BackupBundle: ...

    def local_artifacts_absent(self, operation_id: str) -> bool: ...

    def mark_operation_failed(self, operation_id: str, error_code: str) -> None: ...

    def delete_prepared_local_files(self, bundle: BackupBundle) -> None: ...

    def delete_remaining_local_files(self, operation_id: str) -> None: ...

    def delete_operation_record(self, operation_id: str) -> None: ...


def _is_delete_orphan(operation: DeletableBackupOperation) -> bool:
    return (
        operation.status == "Failed"
        and str(operation.error_summary or "").strip() in DELETE_ORPHAN_ERROR_CODES
    )


def delete_backup_operation(
    *,
    operation_id: str,
    gateway: BackupDeleteGateway,
) -> BackupDeleteResult:
    """Delete one backup operation per Local/Imported/Safety/External policy."""

    op_id = str(operation_id or "").strip()
    if not op_id:
        raise BackupDeleteError("backup_delete_missing_operation")

    operation = gateway.load_operation(op_id)
    orphan = _is_delete_orphan(operation)
    if operation.status == "Completed":
        pass
    elif orphan:
        pass
    else:
        raise BackupDeleteError("backup_delete_not_eligible")

    if operation.operation_type == "Restore" or operation.target == "Restore":
        raise BackupDeleteError("backup_delete_not_eligible")

    if gateway.is_protected_by_active_restore(
        operation_id=operation.operation_id,
        backup_identifier=operation.backup_identifier,
    ):
        raise BackupDeleteError("backup_delete_restore_protected")

    if gateway.is_backup_or_export_busy(
        operation_id=operation.operation_id,
        backup_identifier=operation.backup_identifier,
    ):
        raise BackupDeleteError("backup_delete_operation_busy")

    target = str(operation.target or "").strip()
    op_type = str(operation.operation_type or "").strip()

    if target == "External":
        if op_type not in DELETABLE_EXTERNAL_OPERATION_TYPES:
            raise BackupDeleteError("backup_delete_not_eligible")
        if operation.status != "Completed" and not orphan:
            raise BackupDeleteError("backup_delete_not_eligible")
        try:
            gateway.delete_operation_record(operation.operation_id)
        except BackupDeleteError:
            raise
        except Exception as exc:
            raise BackupDeleteError("backup_delete_record_failed") from exc
        return BackupDeleteResult(
            operation_id=operation.operation_id,
            backup_identifier=operation.backup_identifier,
            target=target,
            operation_type=op_type,
            files_deleted=False,
            record_deleted=True,
            remote_files_deleted=False,
            outcome="record_only_external",
        )

    if target != "Local" or op_type not in DELETABLE_LOCAL_OPERATION_TYPES:
        raise BackupDeleteError("backup_delete_not_eligible")

    shared = gateway.count_other_local_references(
        operation.backup_identifier,
        exclude_operation_id=operation.operation_id,
    )
    if shared > 0:
        if orphan:
            raise BackupDeleteError("backup_delete_not_eligible")
        try:
            gateway.delete_operation_record(operation.operation_id)
        except BackupDeleteError:
            raise
        except Exception as exc:
            raise BackupDeleteError("backup_delete_record_failed") from exc
        return BackupDeleteResult(
            operation_id=operation.operation_id,
            backup_identifier=operation.backup_identifier,
            target=target,
            operation_type=op_type,
            files_deleted=False,
            record_deleted=True,
            remote_files_deleted=False,
            outcome="record_only_shared_refs",
        )

    # Orphan cleanup: prior delete removed files; only the Failed history row remains.
    if orphan and gateway.local_artifacts_absent(operation.operation_id):
        try:
            gateway.delete_operation_record(operation.operation_id)
        except BackupDeleteError:
            raise
        except Exception as exc:
            raise BackupDeleteError("backup_delete_record_failed") from exc
        return BackupDeleteResult(
            operation_id=operation.operation_id,
            backup_identifier=operation.backup_identifier,
            target=target,
            operation_type=op_type,
            files_deleted=False,
            record_deleted=True,
            remote_files_deleted=False,
            outcome="record_only_orphan_cleanup",
        )

    files_deleted = False
    if operation.status == "Completed":
        # Verify full bundle while still Completed, then mark Failed before unlink.
        bundle = gateway.prepare_local_delete_bundle(operation.operation_id)
        gateway.mark_operation_failed(operation.operation_id, "backup_delete_pending")
        try:
            gateway.delete_prepared_local_files(bundle)
            files_deleted = True
        except BackupDeleteError:
            gateway.mark_operation_failed(operation.operation_id, "backup_delete_files_failed")
            raise
        except Exception as exc:
            gateway.mark_operation_failed(operation.operation_id, "backup_delete_files_failed")
            raise BackupDeleteError("backup_delete_files_failed") from exc
    else:
        # Resume after a prior Failed delete marker while some files may remain.
        try:
            gateway.delete_remaining_local_files(operation.operation_id)
            files_deleted = True
        except BackupDeleteError:
            gateway.mark_operation_failed(operation.operation_id, "backup_delete_files_failed")
            raise
        except Exception as exc:
            gateway.mark_operation_failed(operation.operation_id, "backup_delete_files_failed")
            raise BackupDeleteError("backup_delete_files_failed") from exc

    try:
        gateway.delete_operation_record(operation.operation_id)
    except BackupDeleteError as exc:
        gateway.mark_operation_failed(operation.operation_id, "backup_delete_record_failed_after_files")
        if files_deleted:
            raise BackupDeleteError("backup_delete_record_failed_after_files") from exc
        raise
    except Exception as exc:
        gateway.mark_operation_failed(operation.operation_id, "backup_delete_record_failed_after_files")
        raise BackupDeleteError("backup_delete_record_failed_after_files") from exc

    return BackupDeleteResult(
        operation_id=operation.operation_id,
        backup_identifier=operation.backup_identifier,
        target=target,
        operation_type=op_type,
        files_deleted=files_deleted,
        record_deleted=True,
        remote_files_deleted=False,
        outcome="files_and_record",
    )


__all__ = [
    "BackupDeleteError",
    "BackupDeleteGateway",
    "BackupDeleteResult",
    "DELETE_ORPHAN_ERROR_CODES",
    "DELETABLE_EXTERNAL_OPERATION_TYPES",
    "DELETABLE_LOCAL_OPERATION_TYPES",
    "DeletableBackupOperation",
    "delete_backup_operation",
]
