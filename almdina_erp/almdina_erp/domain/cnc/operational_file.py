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
    SHEET_PERIMETER_OPERATION_KEY,
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
FACTORY_PRESET_SOURCE = "Factory"
SHEET_PRESET_SOURCE = "Sheet"

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


def catalog_sheet(
    sheet_no: int,
    pieces: Sequence[Mapping[str, Any]],
    *,
    include_sheet_perimeter: bool = False,
) -> OperationalSheetCatalog:
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
    if include_sheet_perimeter:
        from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY

        operation = operation_for_key(SHEET_PERIMETER_OPERATION_KEY)
        pending.append(
            (operation.sequence, SHEET_PERIMETER_PATH_KEY, SHEET_PERIMETER_OPERATION_KEY, "")
        )
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


def _path_key_is_sheet_perimeter(path_key: str, operation_key: str) -> bool:
    from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY

    key = str(path_key or "").strip()
    operation = str(operation_key or "").strip()
    return (
        operation == SHEET_PERIMETER_OPERATION_KEY
        or key == SHEET_PERIMETER_PATH_KEY
    )


def _path_key_requires_piece_instance(path_key: str) -> bool:
    """True when a persisted path key is bound to one piece instance.

    Shared/anonymous cutter centers use segments like ``cut_path:center:...``
    and may omit a piece id. Sheet perimeter is handled separately.
    """

    from almdina_erp.almdina_erp.domain.cnc.perimeter import (
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        SHEET_PERIMETER_PATH_KEY,
    )

    key = str(path_key or "").strip()
    if not key or key in {SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY}:
        return False
    parts = key.split(":")
    if len(parts) < 2:
        return False
    if parts[0] not in CNC_OPERATIONS_BY_KEY:
        return False
    marker = str(parts[1] or "").strip()
    if marker in {"center", "internals", "sheet_perimeter"}:
        return False
    return bool(marker)


def normalize_path_piece_instance(
    *,
    path_key: str,
    operation_key: str,
    piece_instance_id: str | None,
) -> str:
    """Normalize and enforce piece scope for one operational path row.

    Connected sheet perimeter is sheet-scoped and must keep an empty piece id.
    Piece-bound catalog paths must keep a non-empty piece instance id. Shared
    anonymous paths may omit a piece id when their path key does not embed one.
    """

    identity = str(piece_instance_id or "").strip()
    if _path_key_is_sheet_perimeter(path_key, operation_key):
        if identity:
            raise OperationalFileError("sheet_perimeter_piece_forbidden")
        return ""
    if _path_key_requires_piece_instance(path_key) and not identity:
        raise OperationalFileError("missing_piece_instance_id")
    return identity


def validate_operational_path_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return normalized path rows or raise when piece scope is invalid."""

    normalized: list[dict[str, Any]] = []
    seen_perimeter = False
    from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY

    for raw in rows:
        row = dict(raw)
        path_key = str(row.get("path_key") or "").strip()
        operation_key = str(row.get("operation_key") or "").strip()
        piece_id = normalize_path_piece_instance(
            path_key=path_key,
            operation_key=operation_key,
            piece_instance_id=row.get("piece_instance_id"),
        )
        if path_key == SHEET_PERIMETER_PATH_KEY or operation_key == SHEET_PERIMETER_OPERATION_KEY:
            if seen_perimeter:
                raise OperationalFileError("sheet_perimeter_duplicate")
            seen_perimeter = True
        row["path_key"] = path_key
        row["operation_key"] = operation_key
        row["piece_instance_id"] = piece_id
        normalized.append(row)
    return normalized


def settings_fingerprint(
    *,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    presets: Mapping[str, Mapping[str, Any]],
    machine_profile: Mapping[str, Any] | None = None,
    operation_order: Sequence[str] | None = None,
    cut_path_early_confirmed: bool = False,
    perimeter_join_mode: str = "separate",
    cut_path_sequence: Sequence[str] | None = None,
    perimeter_cut_early_confirmed: bool = False,
    sheet_placement: Mapping[str, Any] | None = None,
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
            "perimeter_join_mode": str(perimeter_join_mode or "separate"),
            "cut_path_sequence": [str(key) for key in (cut_path_sequence or ())],
            "perimeter_cut_early_confirmed": bool(perimeter_cut_early_confirmed),
            "machine_profile": dict(machine_profile or {}),
            "sheet_placement": dict(sheet_placement or {}),
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


def sheet_perimeter_precedes_milling(order: Sequence[str]) -> bool:
    """True when the independent perimeter runs before liner/handle/groove."""

    keys = [str(key) for key in order]
    if SHEET_PERIMETER_OPERATION_KEY not in keys:
        return False
    perimeter_at = keys.index(SHEET_PERIMETER_OPERATION_KEY)
    return any(
        key in keys and keys.index(key) > perimeter_at for key in _INTERNAL_OPERATIONS
    )


def apply_legacy_cut_path_sequence_to_order(
    order: Sequence[str],
    cut_path_sequence: Sequence[str] | None,
    *,
    join_mode: str,
) -> tuple[str, ...]:
    """Map a legacy within-CUT_PATH perimeter sequence onto operation_order.

    ``operation_order`` is the source of truth. Saved ``cut_path_sequence`` only
    nudges ``sheet_perimeter`` relative to ``cut_path`` when connected mode is
    on and the sequence can be interpreted safely.
    """

    keys = [str(key) for key in order]
    if str(join_mode or "").strip() != "connected":
        return tuple(keys)
    if SHEET_PERIMETER_OPERATION_KEY not in keys or "cut_path" not in keys:
        return tuple(keys)
    from almdina_erp.almdina_erp.domain.cnc.perimeter import (
        SHEET_PERIMETER_PATH_KEY,
        coerce_cut_path_sequence_request,
    )

    try:
        coerced = coerce_cut_path_sequence_request(cut_path_sequence)
    except OperationalFileError:
        return tuple(keys)
    if coerced is None:
        return tuple(keys)
    without = [key for key in keys if key != SHEET_PERIMETER_OPERATION_KEY]
    cut_at = without.index("cut_path")
    insert_at = cut_at if coerced[0] == SHEET_PERIMETER_PATH_KEY else cut_at + 1
    without.insert(insert_at, SHEET_PERIMETER_OPERATION_KEY)
    return tuple(without)


def derive_legacy_cut_path_sequence(order: Sequence[str]) -> tuple[str, ...]:
    """Persist a compatibility sequence derived from operation_order."""

    from almdina_erp.almdina_erp.domain.cnc.perimeter import (
        CONNECTED_CUT_PATH_ORDER_KEYS,
        CUT_PATH_INTERNAL_SEQUENCE_KEY,
        SHEET_PERIMETER_PATH_KEY,
    )

    keys = [str(key) for key in order]
    if SHEET_PERIMETER_OPERATION_KEY not in keys or "cut_path" not in keys:
        return ()
    if keys.index(SHEET_PERIMETER_OPERATION_KEY) < keys.index("cut_path"):
        return (SHEET_PERIMETER_PATH_KEY, CUT_PATH_INTERNAL_SEQUENCE_KEY)
    return CONNECTED_CUT_PATH_ORDER_KEYS


def confirmed_operation_order(
    order: Sequence[str],
    *,
    confirmed: bool,
) -> tuple[tuple[str, ...], bool]:
    """Reject an early cut that the user has not explicitly confirmed.

    The stored confirmation does not waive the checks a later generator must
    still run. It only records that this sheet's order was accepted.
    Placing ``sheet_perimeter`` before ``cut_path`` is the default and is not
    an early-cut error.
    """

    normalized = tuple(str(key) for key in order)
    early = cut_path_precedes_internal(normalized)
    if early and not confirmed:
        raise OperationalFileError("cut_path_early_unconfirmed")
    return normalized, bool(early and confirmed)


def confirmed_perimeter_operation_order(
    order: Sequence[str],
    *,
    perimeter_early_confirmed: bool,
) -> tuple[tuple[str, ...], bool]:
    """Warn when the independent perimeter runs before milling add-ons."""

    normalized = tuple(str(key) for key in order)
    early = sheet_perimeter_precedes_milling(normalized)
    if early and not perimeter_early_confirmed:
        raise OperationalFileError("perimeter_cut_early_unconfirmed")
    return normalized, bool(early and perimeter_early_confirmed)


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


def generation_snapshot_is_complete(snapshot: Mapping[str, Any] | None) -> bool:
    """True when a generation snapshot carries the fields required for Generated."""

    if not isinstance(snapshot, Mapping):
        return False
    required = (
        "door_cutting_order",
        "cutting_plan",
        "plan_revision",
        "sheet_no",
        "settings_fingerprint",
        "file_kind",
        "content_sha256",
        "post_processor_version",
        "production",
        "verification_ok",
    )
    for key in required:
        if key not in snapshot:
            return False
    if str(snapshot.get("file_kind") or "") != "simulation":
        return False
    if snapshot.get("production") is True:
        return False
    if not str(snapshot.get("content_sha256") or "").strip():
        return False
    if not str(snapshot.get("settings_fingerprint") or "").strip():
        return False
    return True


def effective_status(
    *,
    generation_fingerprint: str,
    current_fingerprint: str,
    stored_plan: tuple[str, int] | None,
    current_plan: tuple[str, int] | None,
    generated_file: str = "",
    file_present: bool | None = None,
    snapshot_complete: bool | None = None,
) -> str:
    """Return the file status without deleting a previous generation snapshot.

    Generated requires a real persisted NC file reference. A fingerprint alone
    never means the file is ready to download.
    """

    has_file = bool(str(generated_file or "").strip())
    if file_present is False:
        has_file = False
    if not has_file:
        return NOT_GENERATED
    if snapshot_complete is False:
        return NOT_GENERATED
    if not str(generation_fingerprint or "").strip():
        return NOT_GENERATED
    if stored_plan != current_plan:
        return NEEDS_REGENERATION
    if str(generation_fingerprint) != str(current_fingerprint or ""):
        return NEEDS_REGENERATION
    return GENERATED


def _source_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"factory", "sheet"}:
        return token
    if token in {FACTORY_PRESET_SOURCE.lower(), SHEET_PRESET_SOURCE.lower()}:
        return token
    if token:
        raise OperationalFileError("preset_source_invalid")
    return ""


def operation_preset_choice(stored: Any, source: Any, factory_preset: Any) -> tuple[str, str]:
    """Return the effective preset and whether the sheet inherits the factory.

    A blank stored source keeps older rows compatible: a saved name is a sheet
    choice, and a blank name still inherits the current factory default.
    """

    stored_name = str(stored or "").strip()
    factory_name = str(factory_preset or "").strip()
    try:
        token = _source_token(source)
    except OperationalFileError:
        token = ""
    if token == "factory":
        return factory_name, FACTORY_PRESET_SOURCE
    if token == "sheet":
        return stored_name, SHEET_PRESET_SOURCE
    if stored_name:
        return stored_name, SHEET_PRESET_SOURCE
    return factory_name, FACTORY_PRESET_SOURCE


@dataclass(frozen=True, slots=True)
class SheetPresetPlan:
    stored_operations: dict[str, str]
    sources: dict[str, str]
    effective_operations: dict[str, str]
    path_overrides: dict[str, str]


def assign_sheet_presets(
    *,
    catalog: OperationalSheetCatalog,
    operation_presets: Mapping[str, str],
    path_overrides: Mapping[str, str],
    known_presets: Mapping[str, Mapping[str, Any]],
    operation_sources: Mapping[str, str] | None = None,
    factory_defaults: Mapping[str, str] | None = None,
) -> SheetPresetPlan:
    """Validate a sheet setup.

    A factory source stores no preset name, so a later factory default still
    applies. A sheet source stores the chosen name, including an explicit
    blank. Callers that omit sources keep the previous meaning: a name is a
    sheet choice and a blank inherits the factory default.
    """

    present = set(catalog.operations)
    unknown_operations = set(operation_presets).difference(present)
    if unknown_operations or (
        operation_sources is not None and set(operation_sources).difference(present)
    ):
        raise OperationalFileError("unknown_operation")
    path_keys = {path.path_key for path in catalog.paths}
    if set(path_overrides).difference(path_keys):
        raise OperationalFileError("unknown_path")

    defaults = factory_defaults or {}
    supplied = operation_sources is not None
    stored_operations: dict[str, str] = {}
    sources: dict[str, str] = {}
    effective_operations: dict[str, str] = {}
    for key in present:
        requested = str(operation_presets.get(key) or "").strip()
        token = ""
        if supplied and key in (operation_sources or {}):
            token = _source_token((operation_sources or {}).get(key))
        if token == "factory":
            source = FACTORY_PRESET_SOURCE
            stored = ""
            effective = str(defaults.get(key) or "").strip()
        elif token == "sheet":
            source = SHEET_PRESET_SOURCE
            stored = requested
            effective = requested
        elif requested:
            source = SHEET_PRESET_SOURCE
            stored = requested
            effective = requested
        else:
            source = FACTORY_PRESET_SOURCE
            stored = ""
            effective = str(defaults.get(key) or "").strip()
        stored_operations[key] = stored
        sources[key] = source
        effective_operations[key] = effective

    # Connected perimeter reuses the CUT_PATH factory preset by inheritance.
    # A sheet-level choice for sheet_perimeter stays independent.
    if SHEET_PERIMETER_OPERATION_KEY in present:
        dedicated = str(defaults.get(SHEET_PERIMETER_OPERATION_KEY) or "").strip()
        if (
            sources.get(SHEET_PERIMETER_OPERATION_KEY) == FACTORY_PRESET_SOURCE
            and not dedicated
        ):
            inherited = str(effective_operations.get("cut_path") or "").strip()
            if inherited:
                effective_operations[SHEET_PERIMETER_OPERATION_KEY] = inherited

    resolved_paths: dict[str, str] = {}
    used: list[ToolPresetValues] = []
    for path in catalog.paths:
        override = str(path_overrides.get(path.path_key) or "").strip()
        chosen = override or effective_operations.get(path.operation_key, "")
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
    return SheetPresetPlan(
        stored_operations=stored_operations,
        sources=sources,
        effective_operations=effective_operations,
        path_overrides=resolved_paths,
    )


__all__ = [
    "APPROVED_PLAN_STATUS",
    "GENERATED",
    "NEEDS_REGENERATION",
    "NOT_GENERATED",
    "OPERATIONAL_FILE_STATUSES",
    "SYSTEM_PLAN_SOURCE",
    "UPLOADED_PLAN_SOURCE",
    "FACTORY_PRESET_SOURCE",
    "SHEET_PRESET_SOURCE",
    "ApprovedPlanRef",
    "OperationalFileError",
    "OperationalPath",
    "OperationalSheetCatalog",
    "SheetPresetPlan",
    "assert_viewed_plan_token",
    "assess_approved_plan",
    "assign_sheet_presets",
    "apply_legacy_cut_path_sequence_to_order",
    "operation_preset_choice",
    "catalog_sheet",
    "confirmed_operation_order",
    "confirmed_perimeter_operation_order",
    "cut_path_precedes_internal",
    "derive_legacy_cut_path_sequence",
    "default_operation_order",
    "effective_status",
    "sheet_perimeter_precedes_milling",
    "generation_snapshot_is_complete",
    "merge_operation_order",
    "normalize_path_piece_instance",
    "resolve_operation_order",
    "settings_fingerprint",
    "validate_operational_path_rows",
]
