"""Framework-free backup ZIP export format and eligibility rules."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


EXPORT_FORMAT = "almdina.backup.zip"
EXPORT_FORMAT_VERSION = 1
REQUIRED_COMPONENT_NAMES = frozenset(
    {"database", "public_files", "private_files", "site_config"}
)
EXPORTABLE_STATUSES = frozenset({"Completed"})
EXPORTABLE_TARGETS = frozenset({"Local", "External"})
EXPORTABLE_OPERATION_TYPES = frozenset({"Manual", "Scheduled", "Safety", "Imported"})

_SAFE_ARCHIVE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True, slots=True)
class ExportComponent:
    name: str
    path: str
    size: int
    sha256: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class ExportManifest:
    format: str
    format_version: int
    backup_id: str
    operation_id: str
    site: str
    created_at: str
    database_type: str
    target: str
    operation_type: str
    components: tuple[ExportComponent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "format_version": self.format_version,
            "backup_id": self.backup_id,
            "operation_id": self.operation_id,
            "site": self.site,
            "created_at": self.created_at,
            "database_type": self.database_type,
            "target": self.target,
            "operation_type": self.operation_type,
            "components": [
                {
                    "name": component.name,
                    "path": component.path,
                    "size": component.size,
                    "sha256": component.sha256,
                    "required": bool(component.required),
                }
                for component in self.components
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


def archive_member_name(filename: object) -> str:
    """Return a basename-only archive member; reject traversal and absolute paths."""

    raw = str(filename or "").strip()
    if not raw or raw in {".", ".."} or "/" in raw or "\\" in raw or "\x00" in raw:
        raise ValueError("backup_export_invalid_member")
    if raw.startswith(".") or not _SAFE_ARCHIVE_NAME.fullmatch(raw):
        raise ValueError("backup_export_invalid_member")
    return raw


def is_exportable_operation(
    *,
    status: object,
    target: object,
    operation_type: object,
    backup_identifier: object,
) -> bool:
    return (
        str(status or "").strip() in EXPORTABLE_STATUSES
        and str(target or "").strip() in EXPORTABLE_TARGETS
        and str(operation_type or "").strip() in EXPORTABLE_OPERATION_TYPES
        and bool(str(backup_identifier or "").strip())
    )


def build_export_manifest(
    *,
    backup_id: str,
    operation_id: str,
    site: str,
    created_at: str,
    database_type: str,
    target: str,
    operation_type: str,
    components: Sequence[ExportComponent | Mapping[str, Any]],
) -> ExportManifest:
    resolved: list[ExportComponent] = []
    seen_names: set[str] = set()
    seen_paths: set[str] = set()
    for entry in components:
        if isinstance(entry, ExportComponent):
            component = entry
        else:
            component = ExportComponent(
                name=str(entry.get("name") or entry.get("kind") or "").strip(),
                path=archive_member_name(entry.get("path") or entry.get("filename")),
                size=int(entry.get("size") or 0),
                sha256=str(entry.get("sha256") or entry.get("checksum") or "").strip().lower(),
                required=bool(entry.get("required", True)),
            )
        if not component.name or component.name in seen_names:
            raise ValueError("backup_export_invalid_components")
        if component.path in seen_paths:
            raise ValueError("backup_export_invalid_components")
        if component.size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", component.sha256):
            raise ValueError("backup_export_invalid_components")
        seen_names.add(component.name)
        seen_paths.add(component.path)
        resolved.append(
            ExportComponent(
                name=component.name,
                path=archive_member_name(component.path),
                size=component.size,
                sha256=component.sha256,
                required=bool(component.required),
            )
        )

    names = {component.name for component in resolved}
    if names != REQUIRED_COMPONENT_NAMES:
        raise ValueError("backup_export_incomplete_components")

    site_name = str(site or "").strip()
    backup = str(backup_id or "").strip()
    operation = str(operation_id or "").strip()
    created = str(created_at or "").strip()
    db_type = str(database_type or "").strip().lower()
    target_name = str(target or "").strip()
    op_type = str(operation_type or "").strip()
    if not site_name or not backup or not operation or not created or not db_type:
        raise ValueError("backup_export_invalid_manifest")
    if target_name not in EXPORTABLE_TARGETS or op_type not in EXPORTABLE_OPERATION_TYPES:
        raise ValueError("backup_export_invalid_manifest")

    return ExportManifest(
        format=EXPORT_FORMAT,
        format_version=EXPORT_FORMAT_VERSION,
        backup_id=backup,
        operation_id=operation,
        site=site_name,
        created_at=created,
        database_type=db_type,
        target=target_name,
        operation_type=op_type,
        components=tuple(sorted(resolved, key=lambda item: item.name)),
    )


def parse_stored_artifact_manifest(raw: object) -> list[dict[str, Any]]:
    """Parse historical artifact_manifest JSON into exportable component dicts."""

    try:
        entries = json.loads(raw or "[]")
    except (TypeError, ValueError) as exc:
        raise ValueError("backup_export_invalid_manifest") from exc
    if not isinstance(entries, list) or not entries:
        raise ValueError("backup_export_invalid_manifest")

    components: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("backup_export_invalid_manifest")
        item: dict[str, Any] = {
            "name": str(entry.get("kind") or "").strip(),
            "path": archive_member_name(entry.get("filename")),
            "size": int(entry.get("size") or 0),
            "sha256": str(entry.get("checksum") or "").strip().lower(),
            "required": True,
        }
        encryption = str(entry.get("encryption") or "").strip()
        if encryption:
            item["encryption"] = encryption
            item["plaintext_filename"] = str(entry.get("plaintext_filename") or "").strip()
            try:
                item["plaintext_size"] = int(entry.get("plaintext_size") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("backup_export_invalid_manifest") from exc
            item["plaintext_checksum"] = str(entry.get("plaintext_checksum") or "").strip().lower()
        components.append(item)
    return components


__all__ = [
    "EXPORT_FORMAT",
    "EXPORT_FORMAT_VERSION",
    "EXPORTABLE_OPERATION_TYPES",
    "EXPORTABLE_STATUSES",
    "EXPORTABLE_TARGETS",
    "ExportComponent",
    "ExportManifest",
    "REQUIRED_COMPONENT_NAMES",
    "archive_member_name",
    "build_export_manifest",
    "is_exportable_operation",
    "parse_stored_artifact_manifest",
]
