"""Build an Import-compatible almdina.backup.zip from age-encrypted External artifacts.

This module is intended for the operator workstation. It must never receive or
persist an AGE-SECRET-KEY on the application server.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.domain.backups.encryption import (
    AGE_ENCRYPTION_SCHEME,
    is_encrypted_artifact_entry,
)
from almdina_erp.almdina_erp.domain.backups.export_format import (
    EXPORT_FORMAT,
    EXPORT_FORMAT_VERSION,
    REQUIRED_COMPONENT_NAMES,
    archive_member_name,
    build_export_manifest,
)
from almdina_erp.almdina_erp.domain.backups.policy import backup_group_identifier
from almdina_erp.almdina_erp.infrastructure.backups.age_crypto import (
    BackupEncryptionError,
    chunked_sha256,
    decrypt_file_with_age_private_key,
)


class OfflineBackupZipError(RuntimeError):
    """Operator-visible failure while building an Import ZIP offline."""


@dataclass(frozen=True, slots=True)
class OfflinePackageMeta:
    backup_id: str
    operation_id: str
    site: str
    created_at: str
    database_type: str
    target: str
    operation_type: str
    artifacts: tuple[dict[str, Any], ...]


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OfflineBackupZipError(f"Could not read manifest JSON: {path}") from exc


def _read_private_key(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OfflineBackupZipError(f"Could not read private key file: {path}") from exc
    # Prefer the AGE-SECRET-KEY line when the file is age-keygen output.
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("AGE-SECRET-KEY-"):
            return stripped
    stripped = raw.strip()
    if stripped.startswith("AGE-SECRET-KEY-"):
        return stripped
    raise OfflineBackupZipError("Private key file must contain an AGE-SECRET-KEY- identity.")


def parse_offline_manifest(
    payload: object,
    *,
    site: str = "",
    backup_id: str = "",
    database_type: str = "",
    operation_id: str = "",
    created_at: str = "",
    target: str = "",
    operation_type: str = "",
) -> OfflinePackageMeta:
    """Accept either a descriptor object or a bare artifact_manifest list."""

    artifacts_raw: list[Any]
    meta: dict[str, Any] = {}
    if isinstance(payload, list):
        artifacts_raw = payload
    elif isinstance(payload, dict):
        meta = payload
        nested = payload.get("artifacts")
        if nested is None:
            nested = payload.get("components")
        if not isinstance(nested, list):
            raise OfflineBackupZipError("Manifest object must include an artifacts (or components) list.")
        artifacts_raw = nested
    else:
        raise OfflineBackupZipError("Manifest must be a JSON object or list.")

    artifacts: list[dict[str, Any]] = []
    for entry in artifacts_raw:
        if not isinstance(entry, dict):
            raise OfflineBackupZipError("Each artifact entry must be an object.")
        if not is_encrypted_artifact_entry(entry):
            raise OfflineBackupZipError(
                "Offline tool expects encrypted External artifact entries "
                f"(encryption={AGE_ENCRYPTION_SCHEME} or .age filename)."
            )
        kind = str(entry.get("kind") or entry.get("name") or "").strip()
        try:
            cipher_name = archive_member_name(entry.get("filename") or entry.get("path"))
            plain_name = archive_member_name(
                entry.get("plaintext_filename") or str(cipher_name).removesuffix(".age")
            )
            plain_size = int(entry.get("plaintext_size") or 0)
        except (TypeError, ValueError) as exc:
            raise OfflineBackupZipError(f"Invalid artifact metadata for {kind or 'entry'}") from exc
        plain_checksum = str(entry.get("plaintext_checksum") or "").strip().lower()
        if not kind or plain_size <= 0 or len(plain_checksum) != 64:
            raise OfflineBackupZipError(f"Incomplete plaintext metadata for artifact {kind or cipher_name}")
        artifacts.append(
            {
                "kind": kind,
                "filename": cipher_name,
                "plaintext_filename": plain_name,
                "plaintext_size": plain_size,
                "plaintext_checksum": plain_checksum,
                "encryption": str(entry.get("encryption") or AGE_ENCRYPTION_SCHEME),
            }
        )

    if {item["kind"] for item in artifacts} != REQUIRED_COMPONENT_NAMES:
        raise OfflineBackupZipError(
            "Manifest must include encrypted database, public_files, private_files, and site_config."
        )

    resolved_backup_id = str(backup_id or meta.get("backup_id") or "").strip()
    if not resolved_backup_id:
        # Derive from the first plaintext filename when possible.
        site_slug_guess = str(site or meta.get("site") or "").strip().replace(".", "_")
        if site_slug_guess:
            resolved_backup_id = (
                backup_group_identifier(artifacts[0]["plaintext_filename"], site_slug_guess) or ""
            )
    if not resolved_backup_id:
        raise OfflineBackupZipError("backup_id is required (manifest or --backup-id).")

    resolved_site = str(site or meta.get("site") or "").strip()
    if not resolved_site:
        raise OfflineBackupZipError("site is required (manifest or --site).")

    resolved_db = str(database_type or meta.get("database_type") or "mariadb").strip().lower()
    resolved_operation_id = str(operation_id or meta.get("operation_id") or "offline").strip() or "offline"
    resolved_created = str(
        created_at
        or meta.get("created_at")
        or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ).strip()
    resolved_target = str(target or meta.get("target") or "External").strip() or "External"
    resolved_op_type = (
        str(operation_type or meta.get("operation_type") or "Scheduled").strip() or "Scheduled"
    )

    site_slug = resolved_site.replace(".", "_")
    for item in artifacts:
        group = backup_group_identifier(item["plaintext_filename"], site_slug)
        if group != resolved_backup_id:
            raise OfflineBackupZipError(
                f"plaintext filename {item['plaintext_filename']} does not match backup_id {resolved_backup_id}"
            )

    return OfflinePackageMeta(
        backup_id=resolved_backup_id,
        operation_id=resolved_operation_id,
        site=resolved_site,
        created_at=resolved_created,
        database_type=resolved_db,
        target=resolved_target,
        operation_type=resolved_op_type,
        artifacts=tuple(artifacts),
    )


def build_import_zip_from_age_artifacts(
    *,
    cipher_dir: str | Path,
    manifest_path: str | Path,
    private_key_path: str | Path,
    output_zip: str | Path,
    site: str = "",
    backup_id: str = "",
    database_type: str = "",
    operation_id: str = "",
    created_at: str = "",
    target: str = "",
    operation_type: str = "",
) -> Path:
    """Decrypt `.age` artifacts offline and write one Import-compatible ZIP.

    On any failure the destination ZIP is not left behind as a partial package.
    """

    cipher_root = Path(cipher_dir)
    if not cipher_root.is_dir():
        raise OfflineBackupZipError(f"Cipher directory does not exist: {cipher_root}")

    destination = Path(output_zip)
    if destination.exists():
        raise OfflineBackupZipError(f"Output ZIP already exists: {destination}")

    meta = parse_offline_manifest(
        _load_json(Path(manifest_path)),
        site=site,
        backup_id=backup_id,
        database_type=database_type,
        operation_id=operation_id,
        created_at=created_at,
        target=target,
        operation_type=operation_type,
    )
    private_key = _read_private_key(Path(private_key_path))

    work = Path(tempfile.mkdtemp(prefix="almdina-offline-age-zip-"))
    staging = work / "plain"
    staging.mkdir(parents=True, exist_ok=True)
    temp_zip = work / f"{meta.backup_id}.zip"
    try:
        plain_files: list[tuple[str, Path, int, str]] = []
        for artifact in meta.artifacts:
            cipher_path = (cipher_root / artifact["filename"]).resolve()
            try:
                cipher_path.relative_to(cipher_root.resolve())
            except ValueError as exc:
                raise OfflineBackupZipError(f"Cipher file escapes cipher directory: {artifact['filename']}") from exc
            if not cipher_path.is_file():
                raise OfflineBackupZipError(f"Missing encrypted artifact: {artifact['filename']}")

            plain_path = (staging / artifact["plaintext_filename"]).resolve()
            try:
                plain_path.relative_to(staging.resolve())
            except ValueError as exc:
                raise OfflineBackupZipError(
                    f"Plaintext filename escapes staging: {artifact['plaintext_filename']}"
                ) from exc

            try:
                decrypt_file_with_age_private_key(
                    source=cipher_path,
                    destination=plain_path,
                    private_key=private_key,
                )
            except BackupEncryptionError as exc:
                raise OfflineBackupZipError(
                    f"Could not decrypt {artifact['filename']} ({exc.safe_code})."
                ) from exc

            size = plain_path.stat().st_size
            checksum = chunked_sha256(plain_path)
            if size != int(artifact["plaintext_size"]):
                raise OfflineBackupZipError(
                    f"Plaintext size mismatch for {artifact['plaintext_filename']}: "
                    f"expected {artifact['plaintext_size']}, got {size}"
                )
            if checksum != str(artifact["plaintext_checksum"]).lower():
                raise OfflineBackupZipError(
                    f"Plaintext SHA-256 mismatch for {artifact['plaintext_filename']}"
                )
            plain_files.append((artifact["kind"], plain_path, size, checksum))

        try:
            export_manifest = build_export_manifest(
                backup_id=meta.backup_id,
                operation_id=meta.operation_id,
                site=meta.site,
                created_at=meta.created_at,
                database_type=meta.database_type,
                target=meta.target,
                operation_type=meta.operation_type,
                components=[
                    {
                        "name": kind,
                        "path": path.name,
                        "size": size,
                        "sha256": checksum,
                        "required": True,
                    }
                    for kind, path, size, checksum in plain_files
                ],
            )
        except ValueError as exc:
            raise OfflineBackupZipError(f"Could not build Import ZIP manifest: {exc}") from exc

        with zipfile.ZipFile(temp_zip, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr("manifest.json", export_manifest.to_json().encode("utf-8"))
            written = {"manifest.json"}
            for _kind, path, size, checksum in plain_files:
                member = archive_member_name(path.name)
                if member in written:
                    raise OfflineBackupZipError(f"Duplicate ZIP member: {member}")
                if path.stat().st_size != size or chunked_sha256(path) != checksum:
                    raise OfflineBackupZipError(f"Plaintext changed before packing: {member}")
                archive.write(path, arcname=member)
                written.add(member)
            expected = {"manifest.json", *(component.path for component in export_manifest.components)}
            if written != expected:
                raise OfflineBackupZipError("ZIP members do not match export manifest components.")

        with zipfile.ZipFile(temp_zip, mode="r", allowZip64=True) as verify:
            names = set(verify.namelist())
            expected = {"manifest.json", *(component.path for component in export_manifest.components)}
            if names != expected:
                raise OfflineBackupZipError("ZIP verification failed: unexpected members.")
            payload = json.loads(verify.read("manifest.json").decode("utf-8"))
            if payload.get("format") != EXPORT_FORMAT or int(payload.get("format_version") or 0) != EXPORT_FORMAT_VERSION:
                raise OfflineBackupZipError("ZIP verification failed: invalid embedded manifest.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_zip), str(destination))
        return destination.resolve()
    except Exception:
        if destination.exists():
            try:
                destination.unlink()
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


__all__ = [
    "OfflineBackupZipError",
    "OfflinePackageMeta",
    "build_import_zip_from_age_artifacts",
    "parse_offline_manifest",
]
