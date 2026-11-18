"""Plan removal of legacy stored NC attachments without deleting them.

The planner is framework-free. Callers decide whether a later, reviewed
cleanup may delete the exclusive files it lists. This module never deletes.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _legacy_urls(row: Mapping[str, Any]) -> set[str]:
    urls: set[str] = set()
    generated = str(row.get("generated_file") or "").strip()
    if generated:
        urls.add(generated)
    snapshot = _snapshot(row.get("generation_snapshot_json", row.get("generation_snapshot")))
    previous = str(snapshot.get("previous_generated_file") or "").strip()
    if previous:
        urls.add(previous)
    return urls


def _is_nc_name(file_name: str, file_url: str) -> bool:
    token = f"{file_name} {file_url}".lower()
    return token.endswith(".nc") or ".nc?" in token or ".sim.nc" in token


def plan_legacy_nc_cleanup(
    operational_files: Sequence[Mapping[str, Any]],
    files: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a dry-run scope for legacy NC files and their historical fields.

    A file is deletable only when it is an NC attachment of CNC Operational File
    and the same URL is not used by another record. Shared URLs are reported
    and excluded. Nothing in the returned plan is deleted.
    """

    referenced: dict[str, set[str]] = {}
    legacy_rows = 0
    clear_generated = 0
    clear_snapshot = 0
    for row in operational_files:
        name = str(row.get("name") or "")
        urls = _legacy_urls(row)
        snapshot = _snapshot(row.get("generation_snapshot_json", row.get("generation_snapshot")))
        generated = str(row.get("generated_file") or "").strip()
        if generated or snapshot or row.get("generated_by") or row.get("generated_on"):
            legacy_rows += 1
        if generated:
            clear_generated += 1
        if snapshot:
            clear_snapshot += 1
        for url in urls:
            referenced.setdefault(url, set()).add(name)

    attachments: dict[str, list[tuple[str, str]]] = {}
    for file_row in files:
        url = str(file_row.get("file_url") or "").strip()
        if not url:
            continue
        attachments.setdefault(url, []).append(
            (
                str(file_row.get("attached_to_doctype") or ""),
                str(file_row.get("attached_to_name") or ""),
            )
        )

    candidates: set[str] = set()
    for file_row in files:
        url = str(file_row.get("file_url") or "").strip()
        if not url or not _is_nc_name(str(file_row.get("file_name") or ""), url):
            continue
        doctype = str(file_row.get("attached_to_doctype") or "")
        if doctype == "CNC Operational File" or url in referenced:
            candidates.add(url)
    missing = sorted(url for url in referenced if _is_nc_name("", url) and url not in attachments)

    shared: list[str] = []
    exclusive: list[str] = []
    for url in sorted(candidates):
        owners = attachments.get(url, [])
        doctypes = {doctype for doctype, _name in owners}
        names = {name for _doctype, name in owners if name}
        operational_names = {name for name in referenced.get(url, set()) if name}
        shared_attachment = any(doctype != "CNC Operational File" for doctype in doctypes) or len(names) > 1
        shared_reference = len(operational_names) > 1
        if shared_attachment or shared_reference:
            shared.append(url)
        else:
            exclusive.append(url)

    return {
        "dry_run": True,
        "deletes_executed": 0,
        "candidate_file_count": len(candidates),
        "deletable_file_count": len(exclusive),
        "shared_file_count": len(shared),
        "shared_file_urls": shared,
        "deletable_file_urls": exclusive,
        "missing_file_urls": missing,
        "operational_files_with_legacy_fields": legacy_rows,
        "would_clear_generated_file": clear_generated,
        "would_clear_generation_snapshot": clear_snapshot,
    }


__all__ = ["plan_legacy_nc_cleanup"]
