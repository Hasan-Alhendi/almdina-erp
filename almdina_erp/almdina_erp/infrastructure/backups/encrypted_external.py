"""Encrypt local backup artifacts with age before SFTP upload."""

from __future__ import annotations

import tempfile
from pathlib import Path

import frappe

from almdina_erp.almdina_erp.application.backups.management import (
    BackupArtifact,
    BackupBundle,
    ExternalUploadResult,
)
from almdina_erp.almdina_erp.domain.backups.encryption import (
    AGE_ENCRYPTION_SCHEME,
    encrypted_artifact_filename,
    validate_age_public_key,
)
from almdina_erp.almdina_erp.infrastructure.backups.age_crypto import (
    BackupEncryptionError,
    chunked_sha256,
    encrypt_file_with_age_public_key,
)
from almdina_erp.almdina_erp.infrastructure.backups.sftp import SFTPBackupGateway


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


class AgeEncryptedExternalGateway:
    """Wrap SFTP upload so only age ciphertext is stored remotely."""

    def __init__(self, inner: SFTPBackupGateway, *, public_key: str) -> None:
        self._inner = inner
        self._public_key = validate_age_public_key(public_key)

    def test_connection(self) -> None:
        self._inner.test_connection()

    def apply_retention(self, keep_last: int) -> None:
        self._inner.apply_retention(keep_last)

    def upload(self, bundle: BackupBundle) -> ExternalUploadResult:
        private_root = Path(frappe.get_site_path("private")).resolve()
        private_root.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix="almdina-backup-age-", dir=str(private_root))
        ).resolve()
        try:
            encrypted_artifacts: list[BackupArtifact] = []
            for artifact in bundle.artifacts:
                cipher_name = encrypted_artifact_filename(artifact.filename)
                cipher_path = (staging / cipher_name).resolve()
                try:
                    cipher_path.relative_to(staging)
                except ValueError as exc:
                    raise BackupEncryptionError("backup_encryption_failed") from exc
                encrypt_file_with_age_public_key(
                    source=artifact.path,
                    destination=cipher_path,
                    public_key=self._public_key,
                )
                cipher_size = cipher_path.stat().st_size
                cipher_checksum = chunked_sha256(cipher_path)
                encrypted_artifacts.append(
                    BackupArtifact(
                        kind=artifact.kind,
                        path=str(cipher_path),
                        filename=cipher_name,
                        size=cipher_size,
                        checksum=cipher_checksum,
                        plaintext_filename=artifact.filename,
                        plaintext_size=int(artifact.size),
                        plaintext_checksum=str(artifact.checksum),
                        encryption=AGE_ENCRYPTION_SCHEME,
                    )
                )
            encrypted_bundle = BackupBundle(
                identifier=bundle.identifier,
                artifacts=tuple(encrypted_artifacts),
            )
            uploaded = self._inner.upload(encrypted_bundle)
            if isinstance(uploaded, ExternalUploadResult):
                return ExternalUploadResult(
                    reference=uploaded.reference,
                    stored_bundle=encrypted_bundle,
                )
            return ExternalUploadResult(reference=str(uploaded), stored_bundle=encrypted_bundle)
        finally:
            _safe_unlink_tree(staging)


__all__ = ["AgeEncryptedExternalGateway"]
