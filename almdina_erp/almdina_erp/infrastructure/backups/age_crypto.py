"""age/X25519 helpers for external backup ciphertext (server encrypts only)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO

from almdina_erp.almdina_erp.domain.backups.encryption import (
    AGE_ENCRYPTION_SCHEME,
    validate_age_public_key,
)


class BackupEncryptionError(RuntimeError):
    safe_code = "backup_encryption_failed"

    def __init__(self, safe_code: str, *, cause: Exception | None = None) -> None:
        self.safe_code = str(safe_code or "backup_encryption_failed")[:140]
        super().__init__(self.safe_code)
        self.__cause__ = cause


def _recipient(public_key: str):
    try:
        from pyrage import x25519
    except ImportError as exc:
        raise BackupEncryptionError("backup_encryption_unavailable", cause=exc) from exc
    try:
        return x25519.Recipient.from_str(validate_age_public_key(public_key))
    except BackupEncryptionError:
        raise
    except ValueError as exc:
        raise BackupEncryptionError(str(exc) or "backup_encryption_public_key_invalid", cause=exc) from exc
    except Exception as exc:
        raise BackupEncryptionError("backup_encryption_public_key_invalid", cause=exc) from exc


def encrypt_file_with_age_public_key(*, source: str | Path, destination: str | Path, public_key: str) -> None:
    """Encrypt ``source`` to ``destination`` using an age X25519 recipient (streaming)."""

    src = Path(source)
    dst = Path(destination)
    if not src.is_file() or src.is_symlink():
        raise BackupEncryptionError("backup_encryption_source_missing")
    recipient = _recipient(public_key)
    try:
        from pyrage import encrypt_file
    except ImportError as exc:
        raise BackupEncryptionError("backup_encryption_unavailable", cause=exc) from exc
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()
        encrypt_file(str(src), str(dst), [recipient])
    except BackupEncryptionError:
        raise
    except Exception as exc:
        try:
            dst.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupEncryptionError("backup_encryption_failed", cause=exc) from exc
    if not dst.is_file() or dst.stat().st_size <= 0:
        raise BackupEncryptionError("backup_encryption_failed")


def decrypt_file_with_age_private_key(*, source: str | Path, destination: str | Path, private_key: str) -> None:
    """Offline/test helper: decrypt age ciphertext with an operator-held identity.

    Production External Backup / Download paths must never call this with a
    server-stored private key.
    """

    src = Path(source)
    dst = Path(destination)
    secret = str(private_key or "").strip()
    if not secret.startswith("AGE-SECRET-KEY-"):
        raise BackupEncryptionError("backup_encryption_private_key_invalid")
    if not src.is_file() or src.is_symlink():
        raise BackupEncryptionError("backup_encryption_source_missing")
    try:
        from pyrage import decrypt_file
        from pyrage import x25519
    except ImportError as exc:
        raise BackupEncryptionError("backup_encryption_unavailable", cause=exc) from exc
    try:
        identity = x25519.Identity.from_str(secret)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()
        decrypt_file(str(src), str(dst), [identity])
    except BackupEncryptionError:
        raise
    except Exception as exc:
        try:
            dst.unlink(missing_ok=True)
        except OSError:
            pass
        raise BackupEncryptionError("backup_encryption_decrypt_failed", cause=exc) from exc


def chunked_sha256(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encrypt_stream_with_age_public_key(*, reader: BinaryIO, writer: BinaryIO, public_key: str) -> None:
    recipient = _recipient(public_key)
    try:
        from pyrage import encrypt_io
    except ImportError as exc:
        raise BackupEncryptionError("backup_encryption_unavailable", cause=exc) from exc
    try:
        encrypt_io(reader, writer, [recipient])
    except Exception as exc:
        raise BackupEncryptionError("backup_encryption_failed", cause=exc) from exc


__all__ = [
    "AGE_ENCRYPTION_SCHEME",
    "BackupEncryptionError",
    "chunked_sha256",
    "decrypt_file_with_age_private_key",
    "encrypt_file_with_age_public_key",
    "encrypt_stream_with_age_public_key",
]
