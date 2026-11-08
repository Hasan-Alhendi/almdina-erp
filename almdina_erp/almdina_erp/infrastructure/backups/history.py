from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import frappe
from frappe.utils import get_datetime, now, now_datetime

from almdina_erp.almdina_erp.application.backups.management import (
    BackupArtifact,
    BackupBundle,
)
from almdina_erp.almdina_erp.domain.backups.policy import backup_group_identifier
from almdina_erp.almdina_erp.domain.backups.schedule_reliability import (
    ACTIVE_SCHEDULE_STATUSES,
    is_stale_backup_operation,
)
from almdina_erp.almdina_erp.infrastructure.backups.frappe_backup import bundle_manifest


DOCTYPE = "Almdina Backup Operation"


def _canonical_manifest(bundle: BackupBundle) -> str:
    return json.dumps(bundle_manifest(bundle), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest_checksum(manifest: str) -> str:
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def _file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FrappeBackupHistory:
    def create(
        self,
        *,
        operation_type: str,
        target: str,
        requested_by: str,
        schedule_key: str = "",
        source_operation_id: str = "",
    ) -> str:
        operation_id = uuid.uuid4().hex
        frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "operation_id": operation_id,
                "operation_type": operation_type,
                "target": target,
                "status": "Queued",
                "requested_by": requested_by or "Administrator",
                "requested_on": now(),
                "schedule_key": schedule_key or None,
                "source_operation_id": source_operation_id or None,
            }
        ).insert(ignore_permissions=True)
        return operation_id

    def exists_for_schedule(self, schedule_key: str) -> bool:
        """True only when an active/completed operation still owns the schedule key.

        Failed or reclaimed rows release ``schedule_key`` so a later tick can retry
        the same slot without treating a dead record as success.
        """

        key = str(schedule_key or "").strip()
        if not key:
            return False
        return bool(
            frappe.db.exists(
                DOCTYPE,
                {
                    "schedule_key": key,
                    "status": ["in", sorted(ACTIVE_SCHEDULE_STATUSES)],
                },
            )
        )

    def reclaim_stale_operations(self, *, now: datetime | None = None) -> int:
        """Mark stuck Queued/Running/Prepared operations Failed and release their schedule keys."""

        current = now or now_datetime()
        rows = frappe.get_all(
            DOCTYPE,
            filters={"status": ["in", ["Queued", "Running", "Prepared"]]},
            fields=["operation_id", "status", "requested_on", "started_on", "schedule_key"],
            limit_page_length=500,
        )
        reclaimed = 0
        for row in rows:
            requested_on = get_datetime(row.requested_on) if row.requested_on else None
            started_on = get_datetime(row.started_on) if row.started_on else None
            if not is_stale_backup_operation(
                status=row.status,
                requested_on=requested_on,
                started_on=started_on,
                now=current,
            ):
                continue
            self._update(
                row.operation_id,
                {
                    "status": "Failed",
                    "completed_on": now(),
                    "error_summary": "backup_operation_stale_timeout",
                    "schedule_key": None,
                },
            )
            reclaimed += 1
        return reclaimed

    def release_schedule_key(self, operation_id: str) -> None:
        self._update(operation_id, {"schedule_key": None})

    def mark_running(self, operation_id: str) -> None:
        self._update(operation_id, {"status": "Running", "started_on": now(), "error_summary": None})

    def mark_prepared(self, operation_id: str, bundle: BackupBundle) -> None:
        manifest = _canonical_manifest(bundle)
        self._update(
            operation_id,
            {
                "status": "Prepared",
                "backup_identifier": bundle.identifier,
                "reference": bundle.identifier,
                "total_size": bundle.total_size,
                "checksum": _manifest_checksum(manifest),
                "artifact_manifest": manifest,
            },
        )

    def mark_restore_prepared(
        self,
        operation_id: str,
        *,
        source_operation_id: str,
        backup_identifier: str,
        safety_operation_id: str,
    ) -> None:
        self._update(
            operation_id,
            {
                "status": "Prepared",
                "backup_identifier": backup_identifier,
                "reference": safety_operation_id,
                "source_operation_id": source_operation_id,
            },
        )

    def mark_completed(self, operation_id: str, bundle: BackupBundle, reference: str = "") -> None:
        manifest = _canonical_manifest(bundle)
        self._update(
            operation_id,
            {
                "status": "Completed",
                "backup_identifier": bundle.identifier,
                "reference": str(reference or bundle.identifier)[:140],
                "total_size": bundle.total_size,
                "checksum": _manifest_checksum(manifest),
                "artifact_manifest": manifest,
                "completed_on": now(),
                "error_summary": None,
            },
        )

    def create_imported_completed(self, *, bundle: BackupBundle, requested_by: str) -> str:
        """Insert one Completed Local Imported operation after artifacts are on disk."""

        operation_id = uuid.uuid4().hex
        manifest = _canonical_manifest(bundle)
        frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "operation_id": operation_id,
                "operation_type": "Imported",
                "target": "Local",
                "status": "Completed",
                "backup_identifier": bundle.identifier,
                "reference": str(bundle.identifier)[:140],
                "total_size": bundle.total_size,
                "checksum": _manifest_checksum(manifest),
                "artifact_manifest": manifest,
                "requested_by": requested_by or "Administrator",
                "requested_on": now(),
                "started_on": now(),
                "completed_on": now(),
            }
        ).insert(ignore_permissions=True)
        return operation_id

    def imported_backup_identifiers(self) -> set[str]:
        rows = frappe.get_all(
            DOCTYPE,
            filters={"operation_type": "Imported", "status": "Completed", "target": "Local"},
            fields=["backup_identifier"],
            limit_page_length=1000,
        )
        return {str(row.backup_identifier) for row in rows if row.backup_identifier}

    def mark_failed(self, operation_id: str, error_code: str, *, release_schedule: bool = True) -> None:
        values: dict[str, Any] = {
            "status": "Failed",
            "completed_on": now(),
            "error_summary": str(error_code or "backup_operation_failed")[:140],
        }
        if release_schedule:
            values["schedule_key"] = None
        self._update(operation_id, values)

    @staticmethod
    def _update(operation_id: str, values: dict[str, Any]) -> None:
        if not frappe.db.exists(DOCTYPE, operation_id):
            raise ValueError("Backup operation does not exist.")
        frappe.db.set_value(DOCTYPE, operation_id, values, update_modified=False)

    def list_recent(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = frappe.get_all(
            DOCTYPE,
            fields=[
                "operation_id",
                "operation_type",
                "target",
                "status",
                "backup_identifier",
                "reference",
                "total_size",
                "checksum",
                "requested_by",
                "requested_on",
                "started_on",
                "completed_on",
                "source_operation_id",
                "error_summary",
            ],
            order_by="requested_on desc",
            limit_page_length=max(1, min(int(limit), 100)),
        )
        return [dict(row) for row in rows]

    def get(self, operation_id: str) -> dict[str, Any] | None:
        row = frappe.db.get_value(
            DOCTYPE,
            str(operation_id or "").strip(),
            [
                "operation_id",
                "operation_type",
                "target",
                "status",
                "requested_by",
                "requested_on",
                "completed_on",
                "source_operation_id",
            ],
            as_dict=True,
        )
        return dict(row) if row else None

    # Restore remains Manual/Scheduled/Safety only. Imported is downloadable
    # via resolve_local_bundle(..., operation_types=DOWNLOADABLE_LOCAL_OPERATION_TYPES).
    RESTORABLE_OPERATION_TYPES = ("Manual", "Scheduled", "Safety")
    DOWNLOADABLE_LOCAL_OPERATION_TYPES = ("Manual", "Scheduled", "Safety", "Imported")

    def restorable(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = frappe.get_all(
            DOCTYPE,
            filters={
                "target": "Local",
                "status": "Completed",
                "operation_type": ["in", list(self.RESTORABLE_OPERATION_TYPES)],
            },
            fields=["operation_id", "backup_identifier", "requested_on", "total_size", "checksum"],
            order_by="requested_on desc",
            limit_page_length=max(1, min(int(limit), 100)),
        )
        return [dict(row) for row in rows]

    def resolve_local_bundle(
        self,
        operation_id: str,
        *,
        operation_types: tuple[str, ...] | list[str] | None = None,
    ) -> BackupBundle:
        from frappe.utils.backups import get_backup_path

        allowed_types = tuple(operation_types or self.RESTORABLE_OPERATION_TYPES)
        row = frappe.db.get_value(
            DOCTYPE,
            {
                "operation_id": str(operation_id or "").strip(),
                "target": "Local",
                "status": "Completed",
                "operation_type": ["in", list(allowed_types)],
            },
            ["backup_identifier", "artifact_manifest", "checksum"],
            as_dict=True,
        )
        if not row:
            raise ValueError("Backup selection is invalid or unavailable.")
        try:
            entries = json.loads(row.artifact_manifest or "[]")
        except (TypeError, ValueError) as exc:
            raise ValueError("Backup manifest is invalid.") from exc
        if not isinstance(entries, list) or not entries:
            raise ValueError("Backup manifest is invalid.")

        root = Path(get_backup_path()).resolve()
        site_slug = str(frappe.local.site).replace(".", "_")
        artifacts: list[BackupArtifact] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Backup manifest is invalid.")
            filename = str(entry.get("filename") or "")
            path = (root / filename).resolve()
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise ValueError("Backup artifact is outside the approved backup scope.") from exc
            identifier = backup_group_identifier(filename, site_slug)
            if identifier != row.backup_identifier or not path.is_file():
                raise ValueError("Backup artifact is invalid or missing.")
            size = int(entry.get("size") or 0)
            checksum = str(entry.get("checksum") or "")
            if path.stat().st_size != size or not checksum or _file_checksum(path) != checksum:
                raise ValueError("Backup artifact integrity validation failed.")
            artifacts.append(
                BackupArtifact(
                    kind=str(entry.get("kind") or ""),
                    path=str(path),
                    filename=filename,
                    size=size,
                    checksum=checksum,
                )
            )
        bundle = BackupBundle(identifier=str(row.backup_identifier), artifacts=tuple(artifacts))
        canonical = _canonical_manifest(bundle)
        if _manifest_checksum(canonical) != str(row.checksum or ""):
            raise ValueError("Backup manifest integrity validation failed.")
        required = {"database", "public_files", "private_files", "site_config"}
        if {artifact.kind for artifact in artifacts} != required:
            raise ValueError("Backup does not contain all required site artifacts.")
        return bundle


__all__ = ["DOCTYPE", "FrappeBackupHistory"]
