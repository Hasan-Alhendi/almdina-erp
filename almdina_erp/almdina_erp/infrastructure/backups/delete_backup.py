"""Frappe adapter for safe backup operation deletion (no remote SFTP delete)."""

from __future__ import annotations

import json
from pathlib import Path

import frappe

from almdina_erp.almdina_erp.application.backups.delete_backup import (
    BackupDeleteError,
    DeletableBackupOperation,
)
from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle
from almdina_erp.almdina_erp.domain.backups.policy import backup_group_identifier
from almdina_erp.almdina_erp.domain.backups.schedule_reliability import ACTIVE_RESTORE_STATUSES
from almdina_erp.almdina_erp.infrastructure.backups.history import DOCTYPE, FrappeBackupHistory
from almdina_erp.almdina_erp.infrastructure.backups.restore import REQUEST_FOLDER


_ACTIVE_BACKUP_STATUSES = frozenset({"Queued", "Running"})
_EXPORT_STAGING_PREFIXES = ("almdina-backup-export-", "almdina-backup-export-ext-")


def _file_checksum(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FrappeBackupDeleteGateway:
    """Local file + history deletion. Never calls SFTP remove."""

    def __init__(self, *, history: FrappeBackupHistory | None = None) -> None:
        self._history = history or FrappeBackupHistory()

    def load_operation(self, operation_id: str) -> DeletableBackupOperation:
        row = frappe.db.get_value(
            DOCTYPE,
            str(operation_id or "").strip(),
            [
                "operation_id",
                "operation_type",
                "target",
                "status",
                "backup_identifier",
                "error_summary",
            ],
            as_dict=True,
        )
        if not row:
            raise BackupDeleteError("backup_delete_not_found")
        identifier = str(row.backup_identifier or "").strip()
        if not identifier and str(row.target or "") != "Restore":
            raise BackupDeleteError("backup_delete_not_eligible")
        return DeletableBackupOperation(
            operation_id=str(row.operation_id),
            operation_type=str(row.operation_type or ""),
            target=str(row.target or ""),
            status=str(row.status or ""),
            backup_identifier=identifier,
            error_summary=str(row.error_summary or "").strip(),
        )

    def count_other_local_references(
        self,
        backup_identifier: str,
        *,
        exclude_operation_id: str,
    ) -> int:
        identifier = str(backup_identifier or "").strip()
        if not identifier:
            return 0
        rows = frappe.get_all(
            DOCTYPE,
            filters={
                "target": "Local",
                "status": "Completed",
                "backup_identifier": identifier,
                "operation_id": ["!=", str(exclude_operation_id or "").strip()],
            },
            fields=["operation_id"],
            limit_page_length=50,
        )
        return len(rows)

    def is_protected_by_active_restore(
        self,
        *,
        operation_id: str,
        backup_identifier: str,
    ) -> bool:
        op_id = str(operation_id or "").strip()
        identifier = str(backup_identifier or "").strip()
        rows = frappe.get_all(
            DOCTYPE,
            filters={
                "operation_type": "Restore",
                "status": ["in", sorted(ACTIVE_RESTORE_STATUSES)],
            },
            fields=["operation_id", "source_operation_id", "reference", "backup_identifier"],
            limit_page_length=100,
        )
        for row in rows:
            if str(row.source_operation_id or "") == op_id:
                return True
            if str(row.reference or "") == op_id:
                return True
            if identifier and str(row.backup_identifier or "") == identifier:
                return True
            source_id = str(row.source_operation_id or "").strip()
            if source_id and identifier:
                source_identifier = frappe.db.get_value(DOCTYPE, source_id, "backup_identifier")
                if str(source_identifier or "") == identifier:
                    return True
            safety_id = str(row.reference or "").strip()
            if safety_id and identifier and safety_id != source_id:
                safety_identifier = frappe.db.get_value(DOCTYPE, safety_id, "backup_identifier")
                if str(safety_identifier or "") == identifier:
                    return True

        return self._restore_request_protects(operation_id=op_id, backup_identifier=identifier)

    def _restore_request_protects(self, *, operation_id: str, backup_identifier: str) -> bool:
        folder = Path(frappe.get_site_path("private", REQUEST_FOLDER))
        if not folder.is_dir():
            return False
        for path in folder.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            if str(payload.get("source_operation_id") or "") == operation_id:
                return True
            if str(payload.get("safety_operation_id") or "") == operation_id:
                return True
            target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
            safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
            if backup_identifier and str(target.get("identifier") or "") == backup_identifier:
                return True
            if backup_identifier and str(safety.get("identifier") or "") == backup_identifier:
                return True
        return False

    def is_backup_or_export_busy(
        self,
        *,
        operation_id: str,
        backup_identifier: str,
    ) -> bool:
        op_id = str(operation_id or "").strip()
        identifier = str(backup_identifier or "").strip()
        rows = frappe.get_all(
            DOCTYPE,
            filters={"status": ["in", sorted(_ACTIVE_BACKUP_STATUSES)]},
            fields=["operation_id", "backup_identifier", "operation_type", "target"],
            limit_page_length=200,
        )
        for row in rows:
            if str(row.operation_type or "") == "Restore":
                continue
            if str(row.operation_id or "") == op_id:
                return True
            if identifier and str(row.backup_identifier or "") == identifier:
                return True

        return self._export_staging_busy(backup_identifier=identifier)

    def _export_staging_busy(self, *, backup_identifier: str) -> bool:
        identifier = str(backup_identifier or "").strip()
        if not identifier:
            return False
        private_root = Path(frappe.get_site_path("private")).resolve()
        if not private_root.is_dir():
            return False
        for child in private_root.iterdir():
            if not child.is_dir() or child.is_symlink():
                continue
            name = child.name
            if not any(name.startswith(prefix) for prefix in _EXPORT_STAGING_PREFIXES):
                continue
            try:
                for artifact in child.rglob("*"):
                    if artifact.is_file() and identifier in artifact.name:
                        return True
            except OSError:
                continue
        return False

    def mark_operation_failed(self, operation_id: str, error_code: str) -> None:
        self._history.mark_failed(
            str(operation_id or "").strip(),
            str(error_code or "backup_delete_failed")[:140],
            release_schedule=True,
        )

    def prepare_local_delete_bundle(self, operation_id: str) -> BackupBundle:
        """Full integrity resolve while the operation is still Completed."""

        try:
            return self._history.resolve_local_bundle(
                operation_id,
                operation_types=FrappeBackupHistory.DOWNLOADABLE_LOCAL_OPERATION_TYPES,
            )
        except ValueError as exc:
            message = str(exc or "")
            if "integrity" in message.lower():
                raise BackupDeleteError("backup_delete_integrity_failed") from exc
            if "outside" in message.lower():
                raise BackupDeleteError("backup_delete_unsafe_path") from exc
            raise BackupDeleteError("backup_delete_not_eligible") from exc

    def _manifest_entries(self, operation_id: str) -> tuple[str, list[dict]]:
        row = frappe.db.get_value(
            DOCTYPE,
            str(operation_id or "").strip(),
            ["backup_identifier", "artifact_manifest"],
            as_dict=True,
        )
        if not row:
            raise BackupDeleteError("backup_delete_not_found")
        try:
            entries = json.loads(row.artifact_manifest or "[]")
        except (TypeError, ValueError) as exc:
            raise BackupDeleteError("backup_delete_not_eligible") from exc
        if not isinstance(entries, list) or not entries:
            raise BackupDeleteError("backup_delete_not_eligible")
        return str(row.backup_identifier or ""), [entry for entry in entries if isinstance(entry, dict)]

    def local_artifacts_absent(self, operation_id: str) -> bool:
        from frappe.utils.backups import get_backup_path

        _identifier, entries = self._manifest_entries(operation_id)
        root = Path(get_backup_path()).resolve()
        for entry in entries:
            filename = str(entry.get("filename") or "")
            if not filename:
                return False
            path = (root / filename)
            if path.exists() or path.is_symlink():
                return False
        return True

    def _unlink_candidate(self, *, root: Path, filename: str, site_slug: str, identifier: str) -> None:
        candidate = root / filename
        if candidate.is_symlink():
            raise BackupDeleteError("backup_delete_symlink_rejected")
        if not candidate.exists():
            return
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise BackupDeleteError("backup_delete_unsafe_path") from exc
        if path.is_symlink():
            raise BackupDeleteError("backup_delete_symlink_rejected")
        if not path.is_file():
            raise BackupDeleteError("backup_delete_files_failed")
        if backup_group_identifier(path.name, site_slug) != identifier:
            raise BackupDeleteError("backup_delete_unsafe_path")
        if path.name != filename:
            raise BackupDeleteError("backup_delete_unsafe_path")
        try:
            path.unlink()
        except OSError as exc:
            raise BackupDeleteError("backup_delete_files_failed") from exc
        if path.exists():
            raise BackupDeleteError("backup_delete_files_failed")

    def delete_prepared_local_files(self, bundle: BackupBundle) -> None:
        from frappe.utils.backups import get_backup_path

        root = Path(get_backup_path()).resolve()
        site_slug = str(frappe.local.site).replace(".", "_")
        for artifact in bundle.artifacts:
            candidate = root / artifact.filename
            if candidate.is_symlink():
                raise BackupDeleteError("backup_delete_symlink_rejected")
            path = candidate.resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise BackupDeleteError("backup_delete_unsafe_path") from exc
            if path.is_symlink():
                raise BackupDeleteError("backup_delete_symlink_rejected")
            if not path.is_file():
                raise BackupDeleteError("backup_delete_files_failed")
            if backup_group_identifier(path.name, site_slug) != bundle.identifier:
                raise BackupDeleteError("backup_delete_unsafe_path")
            if path.name != artifact.filename:
                raise BackupDeleteError("backup_delete_unsafe_path")
            if path.stat().st_size != int(artifact.size) or _file_checksum(path) != artifact.checksum:
                raise BackupDeleteError("backup_delete_integrity_failed")
            try:
                path.unlink()
            except OSError as exc:
                raise BackupDeleteError("backup_delete_files_failed") from exc
            if path.exists():
                raise BackupDeleteError("backup_delete_files_failed")

    def delete_remaining_local_files(self, operation_id: str) -> None:
        """Resume delete after a Failed marker; skip already-missing members."""

        from frappe.utils.backups import get_backup_path

        identifier, entries = self._manifest_entries(operation_id)
        if not identifier:
            raise BackupDeleteError("backup_delete_not_eligible")
        root = Path(get_backup_path()).resolve()
        site_slug = str(frappe.local.site).replace(".", "_")
        for entry in entries:
            filename = str(entry.get("filename") or "")
            if not filename:
                raise BackupDeleteError("backup_delete_not_eligible")
            self._unlink_candidate(
                root=root,
                filename=filename,
                site_slug=site_slug,
                identifier=identifier,
            )

    def delete_operation_record(self, operation_id: str) -> None:
        name = str(operation_id or "").strip()
        if not name or not frappe.db.exists(DOCTYPE, name):
            raise BackupDeleteError("backup_delete_not_found")
        try:
            frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, delete_permanently=True)
        except Exception as exc:
            raise BackupDeleteError("backup_delete_record_failed") from exc
        if frappe.db.exists(DOCTYPE, name):
            raise BackupDeleteError("backup_delete_record_failed")


__all__ = ["FrappeBackupDeleteGateway"]
