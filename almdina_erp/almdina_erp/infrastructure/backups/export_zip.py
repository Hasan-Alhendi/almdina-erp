"""Secure ZIP packing and export orchestration for Almdina backups."""

from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

import frappe
from werkzeug.utils import send_file
from werkzeug.wrappers import Response

from almdina_erp.almdina_erp.application.backups.export import (
    ExportOperation,
    PackedBackupExport,
    export_backup_zip,
)
from almdina_erp.almdina_erp.application.backups.management import BackupArtifact, BackupBundle
from almdina_erp.almdina_erp.domain.backups.encryption import (
    is_encrypted_artifact_entry,
    manifest_has_encrypted_artifacts,
)
from almdina_erp.almdina_erp.domain.backups.export_format import (
    ExportManifest,
    archive_member_name,
    is_exportable_operation,
    parse_stored_artifact_manifest,
)
from almdina_erp.almdina_erp.domain.backups.policy import backup_group_identifier
from almdina_erp.almdina_erp.infrastructure.backups.history import DOCTYPE, FrappeBackupHistory
from almdina_erp.almdina_erp.infrastructure.backups.sftp import SFTPBackupGateway


class BackupExportError(RuntimeError):
    safe_code = "backup_export_failed"

    def __init__(self, safe_code: str, *, cause: Exception | None = None) -> None:
        self.safe_code = str(safe_code or "backup_export_failed")[:140]
        super().__init__(self.safe_code)
        self.__cause__ = cause


def _chunked_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _safe_unlink(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_symlink() or child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
    except OSError:
        return


def cleanup_export_paths(paths: tuple[str, ...] | list[str]) -> None:
    for raw in paths:
        _safe_unlink(Path(raw))


class StreamingZipPacker:
    """Pack a validated BackupBundle into a temporary ZIP with manifest.json."""

    def __init__(self, *, work_root: Path | None = None) -> None:
        self.work_root = work_root

    def pack(
        self,
        *,
        bundle: BackupBundle,
        manifest: ExportManifest,
        download_stem: str,
    ) -> PackedBackupExport:
        private_root = Path(self.work_root or frappe.get_site_path("private")).resolve()
        private_root.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix="almdina-backup-export-", dir=str(private_root))
        ).resolve()
        if not _inside(private_root, staging):
            raise BackupExportError("backup_export_failed")

        zip_name = f"{archive_member_name(download_stem)}.zip"
        zip_path = (staging / zip_name).resolve()
        try:
            allowed_files = {Path(artifact.path).resolve() for artifact in bundle.artifacts}
            with zipfile.ZipFile(
                zip_path,
                mode="w",
                compression=zipfile.ZIP_STORED,
                allowZip64=True,
            ) as archive:
                manifest_bytes = manifest.to_json().encode("utf-8")
                archive.writestr("manifest.json", manifest_bytes)

                written_members = {"manifest.json"}
                for artifact in bundle.artifacts:
                    member = archive_member_name(artifact.filename)
                    if member in written_members:
                        raise BackupExportError("backup_export_invalid_member")
                    path = Path(artifact.path)
                    if path.is_symlink():
                        raise BackupExportError("backup_export_unsafe_path")
                    resolved = path.resolve()
                    if resolved not in allowed_files:
                        raise BackupExportError("backup_export_unsafe_path")
                    if not resolved.is_file():
                        raise BackupExportError("backup_export_missing_component")
                    size = resolved.stat().st_size
                    if size != int(artifact.size):
                        raise BackupExportError("backup_export_integrity_failed")
                    checksum = _chunked_sha256(resolved)
                    if checksum != str(artifact.checksum).lower():
                        raise BackupExportError("backup_export_integrity_failed")
                    # Stream from disk into the archive; do not preload file bytes.
                    archive.write(resolved, arcname=member)
                    written_members.add(member)

                expected = {"manifest.json", *(component.path for component in manifest.components)}
                if written_members != expected:
                    raise BackupExportError("backup_export_incomplete_components")

            if not zip_path.is_file() or zip_path.stat().st_size <= 0:
                raise BackupExportError("backup_export_failed")
            with zipfile.ZipFile(zip_path, mode="r", allowZip64=True) as verify:
                names = set(verify.namelist())
                if names != expected:
                    raise BackupExportError("backup_export_incomplete_components")
                with verify.open("manifest.json") as handle:
                    payload = json.loads(handle.read().decode("utf-8"))
                if payload.get("format") != manifest.format:
                    raise BackupExportError("backup_export_failed")
                if int(payload.get("format_version") or 0) != int(manifest.format_version):
                    raise BackupExportError("backup_export_failed")

            return PackedBackupExport(
                zip_path=str(zip_path),
                download_name=zip_name,
                manifest=manifest,
                cleanup_paths=(str(staging),),
            )
        except BackupExportError:
            _safe_unlink(staging)
            raise
        except Exception as exc:
            _safe_unlink(staging)
            raise BackupExportError("backup_export_failed", cause=exc) from exc


class FrappeExportOperationRepository:
    def get_export_operation(self, operation_id: str) -> ExportOperation | None:
        row = frappe.db.get_value(
            DOCTYPE,
            str(operation_id or "").strip(),
            [
                "operation_id",
                "operation_type",
                "target",
                "status",
                "backup_identifier",
                "requested_on",
                "completed_on",
                "artifact_manifest",
            ],
            as_dict=True,
        )
        if not row:
            return None
        return ExportOperation(
            operation_id=str(row.operation_id or ""),
            operation_type=str(row.operation_type or ""),
            target=str(row.target or ""),
            status=str(row.status or ""),
            backup_identifier=str(row.backup_identifier or ""),
            completed_on=str(row.completed_on or row.requested_on or ""),
            artifact_manifest=str(row.artifact_manifest or ""),
        )


class FrappeExportBundleResolver:
    """Resolve local backup files or fetch External artifacts over SFTP into a temp scope."""

    def __init__(
        self,
        *,
        sftp_factory: Callable[[], SFTPBackupGateway] | None = None,
        history: FrappeBackupHistory | None = None,
    ) -> None:
        self._sftp_factory = sftp_factory
        self._history = history or FrappeBackupHistory()

    def resolve(self, operation: ExportOperation) -> tuple[BackupBundle, tuple[str, ...]]:
        if operation.target == "Local":
            bundle = self._history.resolve_local_bundle(
                operation.operation_id,
                operation_types=FrappeBackupHistory.DOWNLOADABLE_LOCAL_OPERATION_TYPES,
            )
            return bundle, ()
        if operation.target == "External":
            return self._resolve_external(operation)
        raise BackupExportError("backup_export_not_eligible")

    def _resolve_external(self, operation: ExportOperation) -> tuple[BackupBundle, tuple[str, ...]]:
        if self._sftp_factory is None:
            raise BackupExportError("backup_export_external_unavailable")
        components = parse_stored_artifact_manifest(operation.artifact_manifest)
        if any(is_encrypted_artifact_entry(item) for item in components):
            # Import-compatible ZIP requires plaintext artifacts. Decrypting here
            # would need the operator private key on the server — refused by design.
            raise BackupExportError("backup_export_encrypted_requires_offline_decrypt")
        private_root = Path(frappe.get_site_path("private")).resolve()
        private_root.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix="almdina-backup-export-ext-", dir=str(private_root))
        ).resolve()
        if not _inside(private_root, staging):
            raise BackupExportError("backup_export_failed")

        site_slug = str(frappe.local.site).replace(".", "_")
        gateway = self._sftp_factory()
        try:
            filenames = [str(item["path"]) for item in components]
            gateway.download_artifacts(filenames, str(staging))
            artifacts: list[BackupArtifact] = []
            for item in components:
                filename = archive_member_name(item["path"])
                path = (staging / filename).resolve()
                if path.is_symlink() or not _inside(staging, path) or not path.is_file():
                    raise BackupExportError("backup_export_missing_component")
                identifier = backup_group_identifier(filename, site_slug)
                if identifier != operation.backup_identifier:
                    raise BackupExportError("backup_export_identifier_mismatch")
                size = path.stat().st_size
                checksum = _chunked_sha256(path)
                if size != int(item["size"]) or checksum != str(item["sha256"]):
                    raise BackupExportError("backup_export_integrity_failed")
                artifacts.append(
                    BackupArtifact(
                        kind=str(item["name"]),
                        path=str(path),
                        filename=filename,
                        size=size,
                        checksum=checksum,
                    )
                )
            return (
                BackupBundle(identifier=operation.backup_identifier, artifacts=tuple(artifacts)),
                (str(staging),),
            )
        except BackupExportError:
            _safe_unlink(staging)
            raise
        except Exception as exc:
            _safe_unlink(staging)
            safe = getattr(exc, "safe_code", None)
            raise BackupExportError(str(safe or "backup_export_external_unavailable"), cause=exc) from exc


def _local_backup_identifiers_present(site_slug: str) -> set[str]:
    """One directory scan: identifiers that still have a database artifact on disk."""

    try:
        from frappe.utils.backups import get_backup_path

        root = Path(get_backup_path()).resolve()
    except Exception:
        return set()
    if not root.is_dir():
        return set()
    present: set[str] = set()
    for path in root.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        if not _inside(root, path):
            continue
        identifier = backup_group_identifier(path.name, site_slug)
        if identifier and "-database" in path.name:
            present.add(identifier)
    return present


def annotate_downloadable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark exportable rows. Local rows also require an on-disk database artifact.

    External rows stay metadata-only so the history panel never opens SFTP per row.
    The download endpoint remains the authority and still re-validates fully.
    """

    site_slug = str(getattr(frappe.local, "site", "") or "").replace(".", "_")
    needs_local_probe = any(
        is_exportable_operation(
            status=row.get("status"),
            target=row.get("target"),
            operation_type=row.get("operation_type"),
            backup_identifier=row.get("backup_identifier"),
        )
        and str(row.get("target") or "").strip() == "Local"
        for row in rows
    )
    local_present = _local_backup_identifiers_present(site_slug) if needs_local_probe else set()

    annotated: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        eligible = bool(
            is_exportable_operation(
                status=item.get("status"),
                target=item.get("target"),
                operation_type=item.get("operation_type"),
                backup_identifier=item.get("backup_identifier"),
            )
        )
        if eligible and str(item.get("target") or "").strip() == "Local":
            eligible = str(item.get("backup_identifier") or "") in local_present
        if eligible and str(item.get("target") or "").strip() == "External":
            try:
                import json

                manifest_entries = json.loads(item.get("artifact_manifest") or "[]")
            except (TypeError, ValueError):
                manifest_entries = []
            if manifest_has_encrypted_artifacts(manifest_entries):
                # Keep Download for legacy plaintext External only until an
                # offline-decrypt download path is approved.
                eligible = False
        item["can_download"] = eligible
        annotated.append(item)
    return annotated


def build_backup_zip_export(
    operation_id: str,
    *,
    sftp_factory: Callable[[], SFTPBackupGateway] | None = None,
) -> PackedBackupExport:
    try:
        return export_backup_zip(
            operation_id=operation_id,
            repository=FrappeExportOperationRepository(),
            resolver=FrappeExportBundleResolver(sftp_factory=sftp_factory),
            packer=StreamingZipPacker(),
            site=str(frappe.local.site),
            database_type=str(getattr(frappe.conf, "db_type", None) or "mariadb"),
        )
    except BackupExportError:
        raise
    except ValueError as exc:
        raise BackupExportError(str(exc) or "backup_export_failed", cause=exc) from exc
    except Exception as exc:
        safe = getattr(exc, "safe_code", None)
        raise BackupExportError(str(safe or "backup_export_failed"), cause=exc) from exc


def send_backup_zip_response(packed: PackedBackupExport) -> Response:
    zip_path = Path(packed.zip_path).resolve()
    if not zip_path.is_file():
        cleanup_export_paths(packed.cleanup_paths)
        raise BackupExportError("backup_export_failed")

    response = send_file(
        zip_path,
        environ=frappe.local.request.environ,
        mimetype="application/zip",
        as_attachment=True,
        download_name=packed.download_name,
        conditional=False,
        max_age=0,
    )

    cleanup_paths = tuple(packed.cleanup_paths)
    cleaned = {"done": False}

    def _cleanup_export_staging() -> None:
        if cleaned["done"]:
            return
        cleaned["done"] = True
        cleanup_export_paths(cleanup_paths)

    # Werkzeug closes the response after the WSGI iterator finishes streaming.
    response.call_on_close(_cleanup_export_staging)
    # Frappe's ClosingIterator also runs request.after_response after the body
    # is fully sent, covering client disconnect / proxy edge cases better than
    # patching Response.close alone.
    request = getattr(frappe.local, "request", None)
    after_response = getattr(request, "after_response", None) if request is not None else None
    if after_response is not None and hasattr(after_response, "add"):
        after_response.add(_cleanup_export_staging)
    return response


__all__ = [
    "BackupExportError",
    "FrappeExportBundleResolver",
    "FrappeExportOperationRepository",
    "StreamingZipPacker",
    "annotate_downloadable",
    "build_backup_zip_export",
    "cleanup_export_paths",
    "send_backup_zip_response",
]
