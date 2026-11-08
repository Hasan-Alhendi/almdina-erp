"""Secure ZIP import into the local Frappe backup directory."""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import frappe
from frappe.utils.backups import get_backup_path

from almdina_erp.almdina_erp.application.backups.import_backup import ImportedBackupResult
from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle
from almdina_erp.almdina_erp.domain.backups.import_format import (
    parse_import_manifest_json,
    validate_import_manifest,
)
from almdina_erp.almdina_erp.domain.backups.export_format import archive_member_name
from almdina_erp.almdina_erp.infrastructure.backups.history import FrappeBackupHistory


class BackupImportError(RuntimeError):
    safe_code = "backup_import_failed"

    def __init__(self, safe_code: str, *, cause: Exception | None = None) -> None:
        self.safe_code = str(safe_code or "backup_import_failed")[:140]
        super().__init__(self.safe_code)
        self.__cause__ = cause


_MANIFEST_MEMBER = "manifest.json"
_MANIFEST_MAX_BYTES = 1024 * 1024
_READ_CHUNK = 1024 * 1024


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _safe_unlink_tree(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
            return
        if path.is_dir():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_symlink() or child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
    except OSError:
        return


def _chunked_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    raw = str(info.filename or "").replace("\\", "/")
    if not raw or raw.endswith("/"):
        raise BackupImportError("backup_import_invalid_member")
    if raw.startswith("/") or ".." in raw.split("/"):
        raise BackupImportError("backup_import_unsafe_path")
    if len(raw.split("/")) != 1:
        raise BackupImportError("backup_import_unsafe_path")
    return archive_member_name(raw)


def _reject_encrypted(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise BackupImportError("backup_import_encrypted")


def local_backup_filenames_present(filenames: list[str] | tuple[str, ...]) -> bool:
    root = Path(get_backup_path()).resolve()
    if not root.is_dir():
        return False
    for name in filenames:
        path = (root / archive_member_name(name)).resolve()
        if not _inside(root, path):
            raise BackupImportError("backup_import_unsafe_path")
        if path.exists():
            return True
    return False


class LocalBackupZipImporter:
    """Validate and materialize one Almdina backup ZIP into private/backups."""

    def __init__(self, *, history: FrappeBackupHistory | None = None) -> None:
        self._history = history or FrappeBackupHistory()

    def import_zip(
        self,
        zip_path: str,
        *,
        site: str,
        site_slug: str,
        database_type: str,
        requested_by: str,
    ) -> ImportedBackupResult:
        source = Path(zip_path)
        if not source.is_file() or source.is_symlink():
            raise BackupImportError("backup_import_missing_file")

        private_root = Path(frappe.get_site_path("private")).resolve()
        private_root.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix="almdina-backup-import-", dir=str(private_root))
        ).resolve()
        if not _inside(private_root, staging):
            raise BackupImportError("backup_import_failed")

        finalized: list[Path] = []
        try:
            contract, artifacts = self._extract_verified_artifacts(
                source,
                staging=staging,
                site=site,
                site_slug=site_slug,
                database_type=database_type,
            )
            backup_root = Path(get_backup_path()).resolve()
            backup_root.mkdir(parents=True, exist_ok=True)
            if local_backup_filenames_present([artifact.filename for artifact in artifacts]):
                raise BackupImportError("backup_import_duplicate")

            for artifact in artifacts:
                staged = Path(artifact.path).resolve()
                if staged.is_symlink() or not _inside(staging, staged) or not staged.is_file():
                    raise BackupImportError("backup_import_failed")
                destination = (backup_root / artifact.filename).resolve()
                if not _inside(backup_root, destination):
                    raise BackupImportError("backup_import_unsafe_path")
                if destination.exists():
                    raise BackupImportError("backup_import_duplicate")
                staged.replace(destination)
                finalized.append(destination)

            bundle = BackupBundle(
                identifier=str(contract["backup_id"]),
                artifacts=tuple(
                    BackupArtifact(
                        kind=artifact.kind,
                        path=str((backup_root / artifact.filename).resolve()),
                        filename=artifact.filename,
                        size=artifact.size,
                        checksum=artifact.checksum,
                    )
                    for artifact in artifacts
                ),
            )
            try:
                operation_id = self._history.create_imported_completed(
                    bundle=bundle,
                    requested_by=requested_by,
                )
            except Exception as exc:
                for path in finalized:
                    _safe_unlink_tree(path)
                finalized.clear()
                raise BackupImportError("backup_import_history_failed", cause=exc) from exc

            return ImportedBackupResult(
                operation_id=operation_id,
                backup_identifier=bundle.identifier,
                total_size=bundle.total_size,
            )
        except BackupImportError:
            for path in finalized:
                _safe_unlink_tree(path)
            raise
        except ValueError as exc:
            for path in finalized:
                _safe_unlink_tree(path)
            raise BackupImportError(str(exc) or "backup_import_failed", cause=exc) from exc
        except zipfile.BadZipFile as exc:
            for path in finalized:
                _safe_unlink_tree(path)
            raise BackupImportError("backup_import_corrupt_zip", cause=exc) from exc
        except RuntimeError as exc:
            for path in finalized:
                _safe_unlink_tree(path)
            message = str(exc).lower()
            if "encrypted" in message or "password" in message:
                raise BackupImportError("backup_import_encrypted", cause=exc) from exc
            raise BackupImportError("backup_import_failed", cause=exc) from exc
        except Exception as exc:
            for path in finalized:
                _safe_unlink_tree(path)
            raise BackupImportError("backup_import_failed", cause=exc) from exc
        finally:
            _safe_unlink_tree(staging)

    def _extract_verified_artifacts(
        self,
        source: Path,
        *,
        staging: Path,
        site: str,
        site_slug: str,
        database_type: str,
    ) -> tuple[dict[str, Any], tuple[BackupArtifact, ...]]:
        with zipfile.ZipFile(source, mode="r", allowZip64=True) as archive:
            infos = list(archive.infolist())
            by_name: dict[str, zipfile.ZipInfo] = {}
            for info in infos:
                if info.is_dir():
                    continue
                _reject_encrypted(info)
                name = _zip_member_name(info)
                if name in by_name:
                    raise BackupImportError("backup_import_duplicate_member")
                by_name[name] = info

            if _MANIFEST_MEMBER not in by_name:
                raise BackupImportError("backup_import_missing_manifest")
            manifest_info = by_name[_MANIFEST_MEMBER]
            if int(manifest_info.file_size) <= 0 or int(manifest_info.file_size) > _MANIFEST_MAX_BYTES:
                raise BackupImportError("backup_import_invalid_manifest")

            with archive.open(manifest_info, "r") as handle:
                raw = handle.read(_MANIFEST_MAX_BYTES + 1)
            if len(raw) != int(manifest_info.file_size) or len(raw) > _MANIFEST_MAX_BYTES:
                raise BackupImportError("backup_import_invalid_manifest")
            contract = validate_import_manifest(
                parse_import_manifest_json(raw.decode("utf-8")),
                expected_site=site,
                expected_database_type=database_type,
                site_slug=site_slug,
            )

            expected_members = {_MANIFEST_MEMBER, *(item["path"] for item in contract["components"])}
            if set(by_name) != expected_members:
                raise BackupImportError("backup_import_unexpected_members")

            artifacts: list[BackupArtifact] = []
            for item in contract["components"]:
                info = by_name[item["path"]]
                if int(info.file_size) != int(item["size"]):
                    # Declared uncompressed size must match the verified contract
                    # so Zip-bomb inflation cannot exceed known component sizes.
                    raise BackupImportError("backup_import_integrity_failed")
                destination = (staging / item["path"]).resolve()
                if not _inside(staging, destination):
                    raise BackupImportError("backup_import_unsafe_path")
                digest = hashlib.sha256()
                written = 0
                with archive.open(info, "r") as source_stream, destination.open("wb") as target:
                    while True:
                        chunk = source_stream.read(_READ_CHUNK)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > int(item["size"]):
                            raise BackupImportError("backup_import_zip_bomb")
                        digest.update(chunk)
                        target.write(chunk)
                if written != int(item["size"]):
                    raise BackupImportError("backup_import_integrity_failed")
                checksum = digest.hexdigest()
                if checksum != str(item["sha256"]):
                    raise BackupImportError("backup_import_integrity_failed")
                if destination.stat().st_size != int(item["size"]) or _chunked_sha256(destination) != checksum:
                    raise BackupImportError("backup_import_integrity_failed")
                artifacts.append(
                    BackupArtifact(
                        kind=str(item["name"]),
                        path=str(destination),
                        filename=str(item["path"]),
                        size=int(item["size"]),
                        checksum=checksum,
                    )
                )
            return contract, tuple(artifacts)


def import_local_backup_zip(
    zip_path: str,
    *,
    site: str,
    site_slug: str,
    database_type: str,
    requested_by: str,
) -> ImportedBackupResult:
    return LocalBackupZipImporter().import_zip(
        zip_path,
        site=site,
        site_slug=site_slug,
        database_type=database_type,
        requested_by=requested_by,
    )


__all__ = [
    "BackupImportError",
    "LocalBackupZipImporter",
    "import_local_backup_zip",
    "local_backup_filenames_present",
]
