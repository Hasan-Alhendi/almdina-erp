"""Framework-free rules for validating Almdina backup ZIP imports."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.backups.export_format import (
    EXPORT_FORMAT,
    EXPORT_FORMAT_VERSION,
    REQUIRED_COMPONENT_NAMES,
    archive_member_name,
)
from almdina_erp.almdina_erp.domain.backups.policy import backup_group_identifier


# Manifests produced by export may carry these operation types; Imported packages
# may also re-import a previously imported export.
_IMPORT_MANIFEST_OPERATION_TYPES = frozenset({"Manual", "Scheduled", "Safety", "Imported"})
_IMPORT_MANIFEST_TARGETS = frozenset({"Local", "External"})


def normalize_database_type(value: object) -> str:
    return str(value or "").strip().lower()


def parse_import_manifest_json(raw: object) -> dict[str, Any]:
    try:
        payload = json.loads(raw if isinstance(raw, (bytes, bytearray, str)) else "")
    except (TypeError, ValueError) as exc:
        raise ValueError("backup_import_invalid_manifest") from exc
    if not isinstance(payload, dict):
        raise ValueError("backup_import_invalid_manifest")
    return payload


def validate_import_manifest(
    payload: Mapping[str, Any],
    *,
    expected_site: str,
    expected_database_type: str,
    site_slug: str,
) -> dict[str, Any]:
    """Return a normalized import contract or raise a safe ValueError code."""

    if str(payload.get("format") or "") != EXPORT_FORMAT:
        raise ValueError("backup_import_unsupported_format")
    try:
        version = int(payload.get("format_version"))
    except (TypeError, ValueError) as exc:
        raise ValueError("backup_import_unsupported_format") from exc
    if version != EXPORT_FORMAT_VERSION:
        raise ValueError("backup_import_unsupported_format")

    backup_id = str(payload.get("backup_id") or "").strip()
    site = str(payload.get("site") or "").strip()
    created_at = str(payload.get("created_at") or "").strip()
    database_type = normalize_database_type(payload.get("database_type"))
    target = str(payload.get("target") or "").strip()
    operation_type = str(payload.get("operation_type") or "").strip()
    if not backup_id or not site or not created_at or not database_type:
        raise ValueError("backup_import_invalid_manifest")
    if target not in _IMPORT_MANIFEST_TARGETS or operation_type not in _IMPORT_MANIFEST_OPERATION_TYPES:
        raise ValueError("backup_import_invalid_manifest")
    if site != str(expected_site or "").strip():
        raise ValueError("backup_import_site_mismatch")
    if database_type != normalize_database_type(expected_database_type):
        raise ValueError("backup_import_database_type_mismatch")

    raw_components = payload.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ValueError("backup_import_incomplete_components")

    components: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    for entry in raw_components:
        if not isinstance(entry, dict):
            raise ValueError("backup_import_invalid_manifest")
        name = str(entry.get("name") or "").strip()
        path = archive_member_name(entry.get("path") or entry.get("filename"))
        try:
            size = int(entry.get("size") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("backup_import_invalid_components") from exc
        sha256 = str(entry.get("sha256") or entry.get("checksum") or "").strip().lower()
        if not name or name in seen_names or path in seen_paths:
            raise ValueError("backup_import_invalid_components")
        if size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("backup_import_invalid_components")
        group = backup_group_identifier(path, site_slug)
        if group != backup_id:
            raise ValueError("backup_import_identifier_mismatch")
        seen_names.add(name)
        seen_paths.add(path)
        components.append(
            {
                "name": name,
                "path": path,
                "size": size,
                "sha256": sha256,
                "required": True,
            }
        )

    if {item["name"] for item in components} != REQUIRED_COMPONENT_NAMES:
        raise ValueError("backup_import_incomplete_components")

    return {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "backup_id": backup_id,
        "site": site,
        "created_at": created_at,
        "database_type": database_type,
        "target": target,
        "operation_type": operation_type,
        "components": tuple(sorted(components, key=lambda item: item["name"])),
    }


__all__ = [
    "normalize_database_type",
    "parse_import_manifest_json",
    "validate_import_manifest",
]
