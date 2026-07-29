from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Serialize a plan payload deterministically for audit-safe hashing."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def fingerprint_payload(payload: Mapping[str, Any]) -> str:
    """Return the stable SHA-256 fingerprint of a structured plan payload."""

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def fingerprint_text(value: str | None) -> str:
    """Return the stable SHA-256 fingerprint of one already-canonical text value."""

    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


__all__ = ["canonical_json", "fingerprint_payload", "fingerprint_text"]
