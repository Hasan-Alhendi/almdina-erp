"""Sheet operational-file identity, status, and path catalog.

Geometry stays on the approved cutting plan. This module records which
operational paths exist and which machining preset each one uses.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.operations import (
    CNC_OPERATIONS_BY_KEY,
    DEFAULT_MACHINING_ORDER,
    ILLUSTRATIVE_DXF_LAYERS,
    operation_for_key,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    ToolPresetError,
    ToolPresetValues,
    assert_single_tool_for_file,
    normalize_tool_preset,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import EXTRA_OVERLAY_LAYER_BY_KIND
from almdina_erp.almdina_erp.domain.orders.liner_specs import DoorLinerError, door_liners_from_source


NOT_GENERATED = "Not Generated"
GENERATED = "Generated"
NEEDS_REGENERATION = "Needs Regeneration"
OPERATIONAL_FILE_STATUSES = (NOT_GENERATED, GENERATED, NEEDS_REGENERATION)

APPROVED_PLAN_STATUS = "Approved"
SYSTEM_PLAN_SOURCE = "System"
UPLOADED_PLAN_SOURCE = "Uploaded DXF"
_PLAN_SOURCES = frozenset({SYSTEM_PLAN_SOURCE, UPLOADED_PLAN_SOURCE})
_INTERNAL_OPERATIONS = ("liner", "recessed_handle_cutout", "back_groove")


class OperationalFileError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ApprovedPlanRef:
    name: str
    revision: int
    source_type: str
    status: str

    @property
    def identity(self) -> tuple[str, int]:
        return (self.name, int(self.revision))


@dataclass(frozen=True, slots=True)
class OperationalPath:
    path_key: str
    operation_key: str
    dxf_layer: str
    piece_instance_id: str
    sequence: int


@dataclass(frozen=True, slots=True)
class OperationalSheetCatalog:
    sheet_no: int
    paths: tuple[OperationalPath, ...]

    @property
    def operations(self) -> tuple[str, ...]:
        present: list[str] = []
        for operation in CNC_OPERATIONS_BY_KEY.values():
            if any(path.operation_key == operation.key for path in self.paths):
                present.append(operation.key)
        return tuple(sorted(present, key=lambda key: CNC_OPERATIONS_BY_KEY[key].sequence))


def assess_approved_plan(plan: ApprovedPlanRef | None, *, current: bool) -> ApprovedPlanRef:
    if plan is None or not str(plan.name or "").strip():
        raise OperationalFileError("no_approved_plan")
    if plan.status != APPROVED_PLAN_STATUS or not current:
        if plan.status != APPROVED_PLAN_STATUS:
            raise OperationalFileError("draft_plan" if plan.status == "Draft" else "plan_not_current")
        raise OperationalFileError("plan_not_current")
    if plan.source_type not in _PLAN_SOURCES:
        raise OperationalFileError("unsupported_plan_source")
    if int(plan.revision) <= 0:
        raise OperationalFileError("plan_not_current")
    return plan


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _piece_id(piece: Mapping[str, Any]) -> str:
    identity = str(piece.get("piece_instance_id") or "").strip()
    if not identity:
        raise OperationalFileError("missing_piece_instance_id")
    return identity


def _hole_keys(piece_instance_id: str, geometry: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(geometry, Mapping):
        return []
    holes = geometry.get("holes") or []
    if isinstance(holes, (str, bytes)) or not isinstance(holes, Sequence):
        return []
    ranked = sorted(_fingerprint(hole) for hole in holes)
    keys: list[str] = []
    seen: dict[str, int] = {}
    for digest in ranked:
        seen[digest] = seen.get(digest, 0) + 1
        suffix = digest if seen[digest] == 1 else f"{digest}:{seen[digest]}"
        keys.append(f"cut_path:{piece_instance_id}:hole:{suffix}")
    return keys


def _overlay_paths(piece: Mapping[str, Any], piece_instance_id: str) -> dict[str, list[str]]:
    overlays = piece.get("overlays") or []
    grouped: dict[str, list[str]] = {}
    if isinstance(overlays, (str, bytes)) or not isinstance(overlays, Sequence):
        return grouped
    for overlay in overlays:
        if not isinstance(overlay, Mapping):
            continue
        kind = str(overlay.get("kind") or "").strip()
        layer = str(overlay.get("layer") or "").strip()
        if layer in ILLUSTRATIVE_DXF_LAYERS or kind not in EXTRA_OVERLAY_LAYER_BY_KIND:
            continue
        if kind not in CNC_OPERATIONS_BY_KEY:
            continue
        grouped.setdefault(kind, []).append(
            f"{kind}:{piece_instance_id}:overlay:{_fingerprint(overlay.get('geometry'))}"
        )
    for kind, keys in grouped.items():
        ranked = sorted(keys)
        unique: list[str] = []
        seen: dict[str, int] = {}
        for key in ranked:
            seen[key] = seen.get(key, 0) + 1
            unique.append(key if seen[key] == 1 else f"{key}:{seen[key]}")
        grouped[kind] = unique
    return grouped


def _addon_paths(piece: Mapping[str, Any], piece_instance_id: str, kind: str) -> list[str]:
    if kind == "liner":
        try:
            liners = door_liners_from_source(piece)
        except DoorLinerError as exc:
            raise OperationalFileError("liner_specs_invalid") from exc
        if not liners.enabled:
            return []
        return [f"liner:{piece_instance_id}:{spec.liner_id}" for spec in liners.liners]
    enabled_field = {
        "back_groove": "extra_back_groove",
        "recessed_handle_cutout": "extra_recessed_handle_cutout",
    }[kind]
    if not piece.get(enabled_field):
        return []
    return [f"{kind}:{piece_instance_id}:primary"]


def catalog_sheet(sheet_no: int, pieces: Sequence[Mapping[str, Any]]) -> OperationalSheetCatalog:
    if int(sheet_no) <= 0:
        raise OperationalFileError("sheet_not_in_plan")
    pending: list[tuple[int, str, str, str]] = []
    for piece in pieces:
        if int(piece.get("sheet_no") or 0) != int(sheet_no):
            continue
        identity = _piece_id(piece)
        operation = operation_for_key("cut_path")
        pending.append((operation.sequence, f"cut_path:{identity}:outer", "cut_path", identity))
        for hole_key in _hole_keys(identity, piece.get("geometry") if isinstance(piece.get("geometry"), Mapping) else None):
            pending.append((operation.sequence, hole_key, "cut_path", identity))
        overlays = _overlay_paths(piece, identity)
        for kind in ("liner", "back_groove", "recessed_handle_cutout"):
            keys = overlays.get(kind) or _addon_paths(piece, identity, kind)
            layer_operation = operation_for_key(kind)
            for key in keys:
                pending.append((layer_operation.sequence, key, kind, identity))
    pending.sort(key=lambda item: (item[0], item[3], item[1]))
    paths = tuple(
        OperationalPath(
            path_key=key,
            operation_key=operation_key,
            dxf_layer=operation_for_key(operation_key).dxf_layer,
            piece_instance_id=identity,
            sequence=index,
        )
        for index, (_order, key, operation_key, identity) in enumerate(pending, start=1)
    )
    return OperationalSheetCatalog(sheet_no=int(sheet_no), paths=paths)


def settings_fingerprint(
    *,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    presets: Mapping[str, Mapping[str, Any]],
    machine_profile: Mapping[str, Any] | None = None,
    operation_order: Sequence[str] | None = None,
    cut_path_early_confirmed: bool = False,
) -> str:
    resolved = []
    for key in sorted(set(operation_presets) | set(path_overrides)):
        preset_name = str(path_overrides.get(key) or operation_presets.get(key) or "").strip()
        snapshot = dict(presets.get(preset_name) or {})
        resolved.append({"key": key, "preset": preset_name, "values": snapshot})
    return _fingerprint(
        {
            "assignments": resolved,
            "operation_order": [str(key) for key in (operation_order or ())],
            "cut_path_early_confirmed": bool(cut_path_early_confirmed),
            "machine_profile": dict(machine_profile or {}),
        }
    )


def default_operation_order(present: Sequence[str]) -> tuple[str, ...]:
    present_keys = {str(key) for key in present}
    return tuple(key for key in DEFAULT_MACHINING_ORDER if key in present_keys)


def merge_operation_order(present: Sequence[str], saved: Sequence[str]) -> tuple[str, ...]:
    """Keep a saved order and insert operations that appeared later."""

    present_keys = {str(key) for key in present}
    ordered: list[str] = []
    for raw in saved:
        key = str(raw or "").strip()
        if key in present_keys and key not in ordered:
            ordered.append(key)
    for key in DEFAULT_MACHINING_ORDER:
        if key not in present_keys or key in ordered:
            continue
        insert_at = len(ordered)
        for index, existing in enumerate(ordered):
            if DEFAULT_MACHINING_ORDER.index(existing) > DEFAULT_MACHINING_ORDER.index(key):
                insert_at = index
                break
        ordered.insert(insert_at, key)
    return tuple(ordered)


def resolve_operation_order(present: Sequence[str], requested: Sequence[str]) -> tuple[str, ...]:
    present_keys = {str(key) for key in present}
    ordered: list[str] = []
    for raw in requested:
        key = str(raw or "").strip()
        if key not in present_keys or key in ordered:
            raise OperationalFileError("unknown_operation")
        ordered.append(key)
    if set(ordered) != present_keys:
        raise OperationalFileError("operation_order_incomplete")
    return tuple(ordered)


def cut_path_precedes_internal(order: Sequence[str]) -> bool:
    keys = [str(key) for key in order]
    if "cut_path" not in keys:
        return False
    cut_at = keys.index("cut_path")
    return any(key in keys and keys.index(key) > cut_at for key in _INTERNAL_OPERATIONS)


def confirmed_operation_order(
    order: Sequence[str],
    *,
    confirmed: bool,
) -> tuple[tuple[str, ...], bool]:
    """Reject an early cut that the user has not explicitly confirmed.

    The stored confirmation does not waive the checks a later generator must
    still run. It only records that this sheet's order was accepted.
    """

    normalized = tuple(str(key) for key in order)
    early = cut_path_precedes_internal(normalized)
    if early and not confirmed:
        raise OperationalFileError("cut_path_early_unconfirmed")
    return normalized, bool(early and confirmed)


def assert_viewed_plan_token(plan: ApprovedPlanRef | None, token: str | None) -> None:
    """Reject a save opened against a plan that is no longer the current one."""

    text = str(token or "").strip()
    if not text:
        return
    if plan is None:
        raise OperationalFileError("plan_not_current")
    name, separator, revision = text.partition("::")
    try:
        revision_no = int(revision)
    except ValueError:
        raise OperationalFileError("plan_not_current") from None
    if not separator or name != plan.name or revision_no != int(plan.revision):
        raise OperationalFileError("plan_not_current")


def effective_status(
    *,
    generation_fingerprint: str,
    current_fingerprint: str,
    stored_plan: tuple[str, int] | None,
    current_plan: tuple[str, int] | None,
) -> str:
    """Return the file status without deleting a previous generation snapshot."""

    if not str(generation_fingerprint or "").strip():
        return NOT_GENERATED
    if stored_plan != current_plan:
        return NEEDS_REGENERATION
    if str(generation_fingerprint) != str(current_fingerprint or ""):
        return NEEDS_REGENERATION
    return GENERATED


def assign_sheet_presets(
    *,
    catalog: OperationalSheetCatalog,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    known_presets: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate a sheet setup. Empty preset names mean "not chosen yet"."""

    present = set(catalog.operations)
    unknown_operations = set(operation_presets).difference(present)
    if unknown_operations:
        raise OperationalFileError("unknown_operation")
    path_keys = {path.path_key for path in catalog.paths}
    if set(path_overrides).difference(path_keys):
        raise OperationalFileError("unknown_path")

    resolved_operations = {
        key: str(operation_presets.get(key) or "").strip()
        for key in present
    }
    resolved_paths: dict[str, str] = {}
    used: list[ToolPresetValues] = []
    for path in catalog.paths:
        override = str(path_overrides.get(path.path_key) or "").strip()
        chosen = override or resolved_operations.get(path.operation_key, "")
        if override:
            resolved_paths[path.path_key] = override
        if not chosen:
            continue
        raw = known_presets.get(chosen)
        if raw is None:
            raise OperationalFileError("preset_not_found")
        try:
            preset = normalize_tool_preset(raw)
        except ToolPresetError as exc:
            raise OperationalFileError(exc.code) from exc
        if not preset.enabled:
            raise OperationalFileError("preset_disabled")
        used.append(preset)
    try:
        assert_single_tool_for_file(used)
    except ToolPresetError as exc:
        raise OperationalFileError(exc.code) from exc
    return resolved_operations, resolved_paths


__all__ = [
    "APPROVED_PLAN_STATUS",
    "GENERATED",
    "NEEDS_REGENERATION",
    "NOT_GENERATED",
    "OPERATIONAL_FILE_STATUSES",
    "SYSTEM_PLAN_SOURCE",
    "UPLOADED_PLAN_SOURCE",
    "ApprovedPlanRef",
    "OperationalFileError",
    "OperationalPath",
    "OperationalSheetCatalog",
    "assert_viewed_plan_token",
    "assess_approved_plan",
    "assign_sheet_presets",
    "catalog_sheet",
    "confirmed_operation_order",
    "cut_path_precedes_internal",
    "default_operation_order",
    "effective_status",
    "merge_operation_order",
    "resolve_operation_order",
    "settings_fingerprint",
]
