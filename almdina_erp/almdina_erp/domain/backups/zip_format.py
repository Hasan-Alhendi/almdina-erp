"""Versioned, framework-free contract for a same-site backup package."""
from __future__ import annotations

import re
from typing import Any

from almdina_erp.almdina_erp.domain.backups.policy import backup_group_identifier

FORMAT = "almdina.backup.zip"
VERSION = 1
KINDS = {"database", "public_files", "private_files", "site_config"}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_NAME = re.compile(r"[A-Za-z0-9._-]+\Z")


def validate_manifest(payload: Any, site: str, db_type: str, apps: dict[str, str]) -> tuple[str, tuple[dict, ...]]:
    if not isinstance(payload, dict) or payload.get("format") != FORMAT or type(payload.get("version")) is not int or payload["version"] != VERSION:
        raise ValueError("format")
    if payload.get("site") != site or payload.get("database_type") != db_type:
        raise ValueError("site")
    if payload.get("apps") != apps:
        raise ValueError("versions")
    identifier = payload.get("backup_identifier")
    if not isinstance(identifier, str) or not re.fullmatch(r"\d{8}_\d{6}-[A-Za-z0-9_.-]+", identifier):
        raise ValueError("manifest")
    entries = payload.get("artifacts")
    if not isinstance(entries, list) or len(entries) != 4:
        raise ValueError("artifacts")
    names: set[str] = set()
    kinds: set[str] = set()
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("artifacts")
        kind, name, size, checksum = (row.get(key) for key in ("kind", "filename", "size", "sha256"))
        if (kind not in KINDS or kind in kinds or not isinstance(name, str)
            or name.startswith(".") or not SAFE_NAME.fullmatch(name) or name in names
            or backup_group_identifier(name, site.replace(".", "_")) != identifier
            or type(size) is not int or size <= 0 or not isinstance(checksum, str) or not SHA256.fullmatch(checksum)
            or "-enc" in name):
            raise ValueError("artifacts")
        names.add(name)
        kinds.add(kind)
    if kinds != KINDS:
        raise ValueError("artifacts")
    return identifier, tuple(entries)
