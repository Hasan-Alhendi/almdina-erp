"""Framework-free rules for external backup age/X25519 public-key encryption."""

from __future__ import annotations

import re
from typing import Any, Mapping


AGE_ENCRYPTION_SCHEME = "age-x25519-v1"
AGE_CIPHERTEXT_SUFFIX = ".age"

# Bech32 age X25519 recipient: age1 + lowercase data/checksum alphabet.
_AGE_RECIPIENT_RE = re.compile(r"^age1[02-9ac-hj-np-z]{58,}$")


def normalize_age_public_key(value: object) -> str:
    return str(value or "").strip()


def is_age_public_key_configured(value: object) -> bool:
    return bool(normalize_age_public_key(value))


def validate_age_public_key(value: object) -> str:
    """Return a normalized age recipient string or raise a safe ValueError code."""

    key = normalize_age_public_key(value)
    if not key:
        raise ValueError("backup_encryption_public_key_missing")
    if key.upper().startswith("AGE-SECRET-KEY-"):
        raise ValueError("backup_encryption_private_key_rejected")
    if "\n" in key or "\r" in key or " " in key:
        raise ValueError("backup_encryption_public_key_invalid")
    if not _AGE_RECIPIENT_RE.fullmatch(key):
        raise ValueError("backup_encryption_public_key_invalid")
    return key


def encrypted_artifact_filename(plaintext_filename: object) -> str:
    name = str(plaintext_filename or "").strip()
    if not name or name.endswith(AGE_CIPHERTEXT_SUFFIX):
        raise ValueError("backup_encryption_invalid_filename")
    return f"{name}{AGE_CIPHERTEXT_SUFFIX}"


def is_encrypted_artifact_entry(entry: Mapping[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    scheme = str(entry.get("encryption") or "").strip()
    filename = str(entry.get("filename") or "")
    return scheme == AGE_ENCRYPTION_SCHEME or filename.endswith(AGE_CIPHERTEXT_SUFFIX)


def manifest_has_encrypted_artifacts(entries: object) -> bool:
    if not isinstance(entries, list):
        return False
    return any(is_encrypted_artifact_entry(entry) for entry in entries if isinstance(entry, dict))


__all__ = [
    "AGE_CIPHERTEXT_SUFFIX",
    "AGE_ENCRYPTION_SCHEME",
    "encrypted_artifact_filename",
    "is_age_public_key_configured",
    "is_encrypted_artifact_entry",
    "manifest_has_encrypted_artifacts",
    "normalize_age_public_key",
    "validate_age_public_key",
]
