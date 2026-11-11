"""Use-case wiring for ArtCAM profiles, associations, and frozen toolpaths.

This module does not import Frappe. Geometry stays in the existing compiler.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.artcam_machining import (
    _nc_signature,
    append_snapshot,
    assert_physical_tool_consistency,
    calculate_toolpath_snapshot,
    local_preset_payload,
    machining_public_view,
    normalize_associations,
    normalize_profiles,
    release_stale_toolpath_links,
    synthetic_preset_name,
    vectors_from_paths,
)


def accept_sheet_machining(
    *,
    paths: Sequence[Mapping[str, Any]],
    profiles: Sequence[Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]],
    known_tools: Mapping[str, Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    catalog = vectors_from_paths(paths)
    stored_profiles = normalize_profiles(profiles, known_tools=known_tools)
    stored_associations = normalize_associations(
        associations,
        profiles=stored_profiles,
        catalog=catalog,
        keep_unresolved=True,
    )
    stored_associations = release_stale_toolpath_links(stored_associations, snapshots)
    assert_physical_tool_consistency(stored_associations, snapshots)
    return stored_profiles, stored_associations


def public_sheet_machining(
    *,
    paths: Sequence[Mapping[str, Any]],
    profiles: Sequence[Mapping[str, Any]] | None,
    associations: Sequence[Mapping[str, Any]] | None,
    snapshots: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    return machining_public_view(
        profiles=list(profiles or []),
        associations=list(associations or []),
        snapshots=list(snapshots or []),
        catalog=vectors_from_paths(paths),
    )


def calculation_preset_injection(
    association: Mapping[str, Any],
    known_presets: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Feed the existing compiler the association copy, not the base profile."""

    local = association.get("local_values") if isinstance(association.get("local_values"), Mapping) else {}
    preset_name = synthetic_preset_name(str(association.get("association_id") or ""))
    known = {str(key): dict(value) for key, value in known_presets.items()}
    known[preset_name] = local_preset_payload(local)
    overrides = {
        str(vector_id): preset_name
        for vector_id in association.get("vector_ids") or ()
    }
    return known, overrides


def freeze_calculated_toolpath(
    *,
    association: Mapping[str, Any],
    toolpath_name: str,
    program: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    live_association_ids: Sequence[str] | None = None,
    request_id: str | None = None,
) -> list[dict[str, Any]]:
    snapshot = calculate_toolpath_snapshot(
        association=association,
        toolpath_name=toolpath_name,
        program=program,
        existing_snapshots=snapshots,
        request_id=request_id,
    )
    previous_id = str(association.get("toolpath_id") or "")
    stored = append_snapshot(snapshots, snapshot, live_association_ids=live_association_ids)
    new_id = str(snapshot.get("toolpath_id") or "")
    new_vectors = {str(vector_id) for vector_id in snapshot.get("vector_ids") or ()}
    for row in stored:
        row_id = str(row.get("toolpath_id") or "")
        if row_id == new_id or row.get("superseded_by"):
            continue
        shared = new_vectors.intersection(str(vector_id) for vector_id in row.get("vector_ids") or ())
        if row_id == previous_id or shared:
            row["superseded_by"] = new_id
    return stored


def remember_toolpath_on_association(
    associations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    association_id: str | None = None,
) -> list[dict[str, Any]]:
    """Link only the association that was just calculated, and only when it still matches.

    Recalculating one association must not restore another association's old
    snapshot after its depth, tool, or vectors changed.
    """

    latest: dict[str, Mapping[str, Any]] = {}
    for snapshot in snapshots:
        if isinstance(snapshot, Mapping) and snapshot.get("association_id") and not snapshot.get("archived"):
            latest[str(snapshot.get("association_id"))] = snapshot
    target = str(association_id or "").strip()
    rows: list[dict[str, Any]] = []
    for association in associations:
        row = dict(association)
        row_id = str(row.get("association_id") or "")
        if target and row_id != target:
            rows.append(row)
            continue
        snapshot = latest.get(row_id)
        local = snapshot.get("local_values") if isinstance(snapshot, Mapping) else None
        if isinstance(snapshot, Mapping) and isinstance(local, Mapping):
            current = _nc_signature(row.get("local_values") or {}, row.get("vector_ids") or ())
            frozen = _nc_signature(local, snapshot.get("vector_ids") or ())
            if current == frozen:
                row["toolpath_id"] = snapshot.get("toolpath_id") or ""
                row["toolpath_name"] = snapshot.get("name") or row.get("toolpath_name") or ""
        rows.append(row)
    return rows


__all__ = [
    "accept_sheet_machining",
    "calculation_preset_injection",
    "freeze_calculated_toolpath",
    "public_sheet_machining",
    "remember_toolpath_on_association",
]
