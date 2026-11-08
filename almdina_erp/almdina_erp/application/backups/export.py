"""Backup ZIP export use-case contracts (framework-free)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from almdina_erp.almdina_erp.application.backups.management import BackupBundle
from almdina_erp.almdina_erp.domain.backups.export_format import (
    ExportManifest,
    build_export_manifest,
    is_exportable_operation,
    parse_stored_artifact_manifest,
)


@dataclass(frozen=True, slots=True)
class ExportOperation:
    operation_id: str
    operation_type: str
    target: str
    status: str
    backup_identifier: str
    completed_on: str
    artifact_manifest: str


@dataclass(frozen=True, slots=True)
class PackedBackupExport:
    zip_path: str
    download_name: str
    manifest: ExportManifest
    cleanup_paths: tuple[str, ...]


class ExportOperationRepository(Protocol):
    def get_export_operation(self, operation_id: str) -> ExportOperation | None: ...


class ExportBundleResolver(Protocol):
    def resolve(self, operation: ExportOperation) -> tuple[BackupBundle, tuple[str, ...]]: ...


class BackupZipPacker(Protocol):
    def pack(
        self,
        *,
        bundle: BackupBundle,
        manifest: ExportManifest,
        download_stem: str,
    ) -> PackedBackupExport: ...


def prepare_export_manifest(
    *,
    operation: ExportOperation,
    bundle: BackupBundle,
    site: str,
    database_type: str,
) -> ExportManifest:
    if not is_exportable_operation(
        status=operation.status,
        target=operation.target,
        operation_type=operation.operation_type,
        backup_identifier=operation.backup_identifier,
    ):
        raise ValueError("backup_export_not_eligible")
    if bundle.identifier != operation.backup_identifier:
        raise ValueError("backup_export_identifier_mismatch")

    stored = parse_stored_artifact_manifest(operation.artifact_manifest)
    by_name = {str(item["name"]): item for item in stored}
    components = []
    for artifact in bundle.artifacts:
        stored_entry = by_name.get(artifact.kind)
        if not stored_entry:
            raise ValueError("backup_export_incomplete_components")
        if int(stored_entry["size"]) != int(artifact.size):
            raise ValueError("backup_export_integrity_failed")
        if str(stored_entry["sha256"]) != str(artifact.checksum).lower():
            raise ValueError("backup_export_integrity_failed")
        components.append(
            {
                "name": artifact.kind,
                "path": artifact.filename,
                "size": artifact.size,
                "sha256": artifact.checksum,
                "required": True,
            }
        )
    return build_export_manifest(
        backup_id=operation.backup_identifier,
        operation_id=operation.operation_id,
        site=site,
        created_at=operation.completed_on,
        database_type=database_type,
        target=operation.target,
        operation_type=operation.operation_type,
        components=components,
    )


def export_backup_zip(
    *,
    operation_id: str,
    repository: ExportOperationRepository,
    resolver: ExportBundleResolver,
    packer: BackupZipPacker,
    site: str,
    database_type: str,
) -> PackedBackupExport:
    operation = repository.get_export_operation(operation_id)
    if operation is None:
        raise ValueError("backup_export_not_found")
    if not is_exportable_operation(
        status=operation.status,
        target=operation.target,
        operation_type=operation.operation_type,
        backup_identifier=operation.backup_identifier,
    ):
        raise ValueError("backup_export_not_eligible")

    cleanup: list[str] = []
    try:
        bundle, fetched_cleanup = resolver.resolve(operation)
        cleanup.extend(fetched_cleanup)
        manifest = prepare_export_manifest(
            operation=operation,
            bundle=bundle,
            site=site,
            database_type=database_type,
        )
        packed = packer.pack(
            bundle=bundle,
            manifest=manifest,
            download_stem=operation.backup_identifier,
        )
        return PackedBackupExport(
            zip_path=packed.zip_path,
            download_name=packed.download_name,
            manifest=packed.manifest,
            cleanup_paths=tuple([*cleanup, *packed.cleanup_paths]),
        )
    except Exception:
        for path in cleanup:
            _safe_remove(path)
        raise


def _safe_remove(path: str) -> None:
    from pathlib import Path

    candidate = Path(path)
    try:
        if candidate.is_file() or candidate.is_symlink():
            candidate.unlink(missing_ok=True)
        elif candidate.is_dir():
            for child in sorted(candidate.rglob("*"), reverse=True):
                if child.is_file() or child.is_symlink():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            candidate.rmdir()
    except OSError:
        return


__all__ = [
    "BackupZipPacker",
    "ExportBundleResolver",
    "ExportOperation",
    "ExportOperationRepository",
    "PackedBackupExport",
    "export_backup_zip",
    "prepare_export_manifest",
]
