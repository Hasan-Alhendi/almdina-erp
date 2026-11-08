"""Backup ZIP import use-case contracts (framework-free)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ImportedBackupResult:
    operation_id: str
    backup_identifier: str
    total_size: int


class BackupImportGateway(Protocol):
    def import_zip(
        self,
        zip_path: str,
        *,
        site: str,
        site_slug: str,
        database_type: str,
        requested_by: str,
    ) -> ImportedBackupResult: ...


def import_backup_zip(
    *,
    zip_path: str,
    gateway: BackupImportGateway,
    site: str,
    site_slug: str,
    database_type: str,
    requested_by: str,
) -> ImportedBackupResult:
    if not str(zip_path or "").strip():
        raise ValueError("backup_import_missing_file")
    return gateway.import_zip(
        str(zip_path),
        site=site,
        site_slug=site_slug,
        database_type=database_type,
        requested_by=requested_by,
    )


__all__ = [
    "BackupImportGateway",
    "ImportedBackupResult",
    "import_backup_zip",
]
