"""Board-editor operational projection over an already-trusted plan snapshot.

Read model only: no moves, no CUT_PATH generation, no snapshot rewrite, no
parallel store. View/session settings stay separate from manufacturing truth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    is_financial_plan_key,
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_hosting import (
    declared_host_piece_id,
    hosting_forest_for_pieces,
    piece_placement_id,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_COORDINATE_SPACE,
    GEOMETRY_UNIT,
    serialize_geometry_mm,
    serialize_overlay_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_layer_catalog import (
    AFFILIATION_MAY_SPAN_MULTIPLE_PIECES,
    AFFILIATION_NEVER_INFER_FROM_LAYER,
    BOARD_EDITOR_LAYER_SCHEMA_VERSION,
    COLOR_SOURCE_BYENTITY,
    COLOR_SOURCE_BYLAYER,
    COLOR_SOURCE_CATALOG_DEFAULT,
    CUT_PATH_LAYER,
    GEOMETRY_LAYER,
    LINETYPE_SOURCE_BYENTITY,
    LINETYPE_SOURCE_BYLAYER,
    LINETYPE_SOURCE_CATALOG_DEFAULT,
    OFFCUT_LAYER,
    SHEET_OUTLINE_LAYER,
    TEXT_LAYER_EXPORT_NAME,
    build_layer_registry,
    layer_match_key,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    material_outline_cm,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
    liner_centerline_mm,
    obstacle_geometry_mm,
    piece_quarter_turns,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    MACHINING_ADDONS,
    machining_metadata,
    machining_values,
)
from almdina_erp.almdina_erp.domain.cutting.physical_execution_contract import (
    PHYSICAL_EXECUTION_CONTRACT,
    is_legacy_physical_execution_snapshot,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    EXTRA_OVERLAY_LAYER_BY_KIND,
    extra_overlay_layer_for_kind,
)
from almdina_erp.almdina_erp.domain.orders.liner_specs import DoorLinerError
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    CLIPPED_CORNER_TYPE,
    GLASS_TYPE,
    L_SHAPED_CORNER_TYPE,
)

BOARD_EDITOR_PROJECTION_SCHEMA_VERSION = 1

ELEMENT_KIND_SHEET_OUTLINE = "sheet_outline"
ELEMENT_KIND_FINISHED_OUTLINE = "finished_outline"
ELEMENT_KIND_HOLE = "hole"
ELEMENT_KIND_OVERLAY = "addon_overlay"
ELEMENT_KIND_TEXT = "text_label"
ELEMENT_KIND_REFERENCE = "reference"
ELEMENT_KIND_UNRESOLVED = "unresolved"
ELEMENT_KIND_PLACEMENT_RECT = "placement_rect"

AFFILIATION_BOUND = "bound"
AFFILIATION_SHEET = "sheet"
AFFILIATION_UNRESOLVED = "unresolved"
AFFILIATION_REFERENCE = "reference"

CONTENT_STATE_EMPTY = "empty"
CONTENT_STATE_PROJECTED = "projected"
CONTENT_STATE_UNAVAILABLE = "unavailable"

SUPPORT_LIMIT_NO_CUT_PATH_GENERATION = (
    "CUT_PATH manufacturing paths are not generated for the editor projection; "
    "when saw centers exist only in the source file or post-approval export they "
    "are marked content_unavailable unless supplied as reference entities."
)
SUPPORT_LIMIT_TEXT_NOT_BOUND_BY_LAYER = (
    "TEXT annotations are never bound to a door from layer name alone."
)
SUPPORT_LIMIT_REFERENCE_ENTITIES = (
    "Reference/unsupported DXF entities stay unbound; affiliation is never guessed."
)
SUPPORT_LIMIT_HISTORICAL_SNAPSHOT = (
    "Historical snapshots are consumed as-is; missing piece_instance_id is preserved."
)
SUPPORT_LIMIT_SPECIAL_WITHOUT_GEOMETRY = (
    "Special pieces without persisted DXF geometry, exact special-shape JSON, "
    "or trusted CNC-raw placement dimensions stay non-editable."
)
SUPPORT_LIMIT_SPECIAL_CNC_RAW = (
    "Special CNC-raw stock uses the trusted placement rectangle for layout only; "
    "it is not a final CNC cut contour."
)
GEOMETRY_SOURCE_CNC_RAW = "cnc_raw_rect"
GEOMETRY_SOURCE_SPECIAL_JSON = "special_shape_geometry_json"
GEOMETRY_SOURCE_UNAVAILABLE = "unavailable"

MAX_REFERENCE_ENTITIES = 5_000


def _nested_has_financial(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if is_financial_plan_key(key):
                return True
            if _nested_has_financial(item):
                return True
        return False
    if isinstance(value, list):
        return any(_nested_has_financial(item) for item in value)
    return False


def _sanitize_auxiliary(value: Any) -> Any:
    """Strip financial keys from auxiliary inputs (layer_table / references)."""

    if isinstance(value, Mapping):
        return {
            key: _sanitize_auxiliary(item)
            for key, item in value.items()
            if not is_financial_plan_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_auxiliary(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_auxiliary(item) for item in value]
    return value


def default_board_editor_view_settings() -> dict[str, Any]:
    """Future UI session state. Never treated as manufacturing authority."""

    return {
        "layer_visibility": {},
        "selected_element_ids": [],
        "selected_piece_ids": [],
        "selected_sheet_no": None,
        "zoom": None,
        "pan": None,
    }


def _stable_piece_token(piece: Mapping[str, Any], *, sheet_no: int) -> str:
    piece_id = piece_placement_id(piece)
    if piece_id is not None:
        return f"sheet:{sheet_no}:piece:{piece_id}"
    instance_id = str(piece.get("piece_instance_id") or "").strip()
    if instance_id:
        return f"sheet:{sheet_no}:instance:{instance_id}"
    label = str(piece.get("label") or "").strip() or "unknown"
    return f"sheet:{sheet_no}:label:{label}"


def _explicit_allow_rotation(piece: Mapping[str, Any]) -> bool | None:
    """Return True/False when the order flag is proven; None when absent.

    ``allow_rotation_proven`` means the value was established from a trusted
    source. It is not itself permission. Absence must not grant rotation.
    """

    if "allow_rotation" not in piece and "allow_rotation_proven" not in piece:
        return None
    if "allow_rotation_proven" in piece and piece.get("allow_rotation_proven") is False:
        return None
    if "allow_rotation" not in piece:
        return None
    flag = piece.get("allow_rotation")
    if flag is True or flag == 1 or flag == "1":
        return True
    if flag is False or flag == 0 or flag == "0":
        return False
    return None


def _fill_role_for_piece(piece: Mapping[str, Any], *, sheet_resource_kind: str = "") -> str:
    resource = str(
        piece.get("resource_kind") or sheet_resource_kind or ""
    ).strip().upper()
    if resource == OFFCUT_LAYER:
        return "offcut"
    piece_type = str(piece.get("piece_type") or "")
    if piece_type == GLASS_TYPE:
        return "glass"
    if piece_type == "Special":
        return "special"
    if piece_type == L_SHAPED_CORNER_TYPE:
        return "l_shaped"
    if piece_type == CLIPPED_CORNER_TYPE:
        return "clipped_corner"
    return "regular"


def _display_edges(piece: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "edge_long_right": bool(piece.get("edge_long_right")),
        "edge_long_left": bool(piece.get("edge_long_left")),
        "edge_width_top": bool(piece.get("edge_width_top")),
        "edge_width_bottom": bool(piece.get("edge_width_bottom")),
        "edge_break": bool(piece.get("edge_break")),
        "edge_break_only": bool(piece.get("edge_break_only")),
        "extra_double": bool(piece.get("extra_double")),
        "extra_full_door_double": bool(piece.get("extra_full_door_double")),
        "extra_double_reference_sides": str(
            piece.get("extra_double_reference_sides") or ""
        ),
        "edge_long_type": str(piece.get("edge_long_type") or ""),
        "edge_width_type": str(piece.get("edge_width_type") or ""),
        "edge_type": str(piece.get("edge_type") or ""),
        "edge_long_left_type_override": str(piece.get("edge_long_left_type_override") or ""),
        "edge_long_right_type_override": str(piece.get("edge_long_right_type_override") or ""),
        "edge_width_top_type_override": str(piece.get("edge_width_top_type_override") or ""),
        "edge_width_bottom_type_override": str(piece.get("edge_width_bottom_type_override") or ""),
    }


def _liner_piece_from_placed(piece: Mapping[str, Any]) -> LinerPiece | None:
    width = float(
        piece.get("cut_width_cm")
        or piece.get("width_cm")
        or piece.get("original_w")
        or piece.get("w")
        or 0
    )
    length = float(
        piece.get("cut_length_cm")
        or piece.get("length_cm")
        or piece.get("original_h")
        or piece.get("h")
        or 0
    )
    if width <= 0 or length <= 0:
        return None
    return LinerPiece(
        str(piece.get("piece_type") or "Regular"),
        width,
        length,
        str(piece.get("clipped_corner_position") or "Top Right"),
        float(piece.get("clipped_corner_width_cm") or 0),
        float(piece.get("clipped_corner_length_cm") or 0),
    )


def _place_local_path_mm(
    piece: Mapping[str, Any],
    liner: LinerPiece,
    local_path: Sequence[Sequence[float]],
) -> list[list[float]]:
    turns = piece_quarter_turns(piece)
    mirrored = bool(piece.get("corner_mirrored"))
    origin_x = float(piece.get("x") or 0) * 10.0
    origin_y = float(piece.get("y") or 0) * 10.0
    width = float(liner.width_cm) * 10.0
    height = float(liner.length_cm) * 10.0
    placed: list[list[float]] = []
    for point in local_path:
        if not isinstance(point, Sequence) or len(point) != 2:
            continue
        moved = transform_point(
            (float(point[0]), float(point[1])),
            mirrored=mirrored,
            quarter_turns=turns,
            width=width,
            height=height,
        )
        placed.append([moved[0] + origin_x, moved[1] + origin_y])
    return placed


def _parametric_material_geometry(
    piece: Mapping[str, Any],
) -> tuple[dict[str, Any], str] | None:
    """Usable-sheet outline from existing engines; never invents Special contours."""

    piece_type = str(piece.get("piece_type") or "")
    if piece_type == "Special":
        return None
    try:
        info = obstacle_geometry_mm(piece)
    except (LinerGeometryError, TypeError, ValueError):
        return None
    outer = info.get("outer") or []
    if not isinstance(outer, Sequence) or len(outer) < 3:
        return None
    holes_raw = info.get("holes") or []
    holes: list[tuple[tuple[float, float], ...]] = []
    if isinstance(holes_raw, Sequence):
        for hole in holes_raw:
            if not isinstance(hole, Sequence) or len(hole) < 3:
                continue
            holes.append(tuple((float(point[0]), float(point[1])) for point in hole))
    geometry = serialize_geometry_mm(
        PartGeometry(
            outer=tuple((float(point[0]), float(point[1])) for point in outer),
            holes=tuple(holes),
        )
    )
    source = str(info.get("source") or "parametric")
    return geometry, source


def _finite_dim(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _special_exact_geometry_mm(piece: Mapping[str, Any]) -> dict[str, Any] | None:
    """Exact Special contour from trusted special_shape_geometry_json (usable-sheet mm)."""

    outline_cm = material_outline_cm(piece)
    if outline_cm is None or len(outline_cm) < 3:
        return None
    return serialize_geometry_mm(
        PartGeometry(
            outer=tuple((float(point[0]) * 10.0, float(point[1]) * 10.0) for point in outline_cm),
            holes=(),
        )
    )


def _cnc_raw_dims_trusted(piece: Mapping[str, Any]) -> bool:
    """True when the plan supplies a trusted Special CNC-raw stock rectangle."""

    width = _finite_dim(piece.get("w"))
    height = _finite_dim(piece.get("h"))
    if width is None or height is None or width <= 0 or height <= 0:
        return False
    # Origin may be zero; reject only non-finite coordinates.
    if _finite_dim(piece.get("x")) is None or _finite_dim(piece.get("y")) is None:
        return False
    return True


def _cnc_raw_rect_geometry_mm(piece: Mapping[str, Any]) -> dict[str, Any] | None:
    """Axis-aligned CNC-raw stock rectangle in usable-sheet millimetres."""

    if not _cnc_raw_dims_trusted(piece):
        return None
    x = float(piece.get("x") or 0) * 10.0
    y = float(piece.get("y") or 0) * 10.0
    width = float(piece.get("w")) * 10.0
    height = float(piece.get("h")) * 10.0
    if bool(piece.get("rotated")):
        width, height = height, width
    return serialize_geometry_mm(
        PartGeometry(
            outer=(
                (x, y),
                (x + width, y),
                (x + width, y + height),
                (x, y + height),
            ),
            holes=(),
        )
    )


def _geometry_source_for_piece(piece: Mapping[str, Any]) -> str:
    if isinstance(piece.get("geometry"), Mapping):
        return "persisted_dxf"
    piece_type = str(piece.get("piece_type") or "")
    if piece_type == "Special":
        if _special_exact_geometry_mm(piece) is not None:
            return GEOMETRY_SOURCE_SPECIAL_JSON
        if _cnc_raw_dims_trusted(piece):
            return GEOMETRY_SOURCE_CNC_RAW
        return GEOMETRY_SOURCE_UNAVAILABLE
    parametric = _parametric_material_geometry(piece)
    if parametric is None:
        return "placement_rect"
    return str(parametric[1] or "parametric")


def _piece_identity(piece: Mapping[str, Any], *, sheet_no: int | None) -> dict[str, Any]:
    placement_id = piece_placement_id(piece)
    instance_id = str(piece.get("piece_instance_id") or "").strip() or None
    allow = _explicit_allow_rotation(piece)
    overlay_count = (
        len(piece.get("overlays") or [])
        if isinstance(piece.get("overlays"), list)
        else 0
    )
    geometry_source = _geometry_source_for_piece(piece)
    return {
        "piece_id": placement_id,
        "piece_instance_id": instance_id,
        "label": str(piece.get("label") or ""),
        "source_piece_no": piece.get("source_piece_no"),
        "copy_no": piece.get("copy_no"),
        "sheet_no": sheet_no,
        "piece_type": str(piece.get("piece_type") or ""),
        "resource_kind": str(piece.get("resource_kind") or "").strip().upper() or None,
        "offcut_source_party": str(piece.get("offcut_source_party") or "").strip().upper() or None,
        "offcut_execution_party": str(piece.get("offcut_execution_party") or "").strip().upper()
        or None,
        "placement_cm": {
            "x": piece.get("x"),
            "y": piece.get("y"),
            "w": piece.get("w"),
            "h": piece.get("h"),
            "rotated": bool(piece.get("rotated")),
        },
        "glass_host_piece_id": declared_host_piece_id(piece),
        "glass_hole_local_mm": deepcopy(piece.get("glass_hole_local_mm"))
        if piece.get("glass_hole_local_mm") is not None
        else None,
        "has_geometry": isinstance(piece.get("geometry"), Mapping)
        or geometry_source
        not in {"placement_rect", "unavailable"},
        "overlay_count": overlay_count,
        "geometry_source": geometry_source,
        "fill_role": _fill_role_for_piece(piece),
        "display_edges": _display_edges(piece),
        "clipped_corner_position": str(piece.get("clipped_corner_position") or ""),
        "clipped_corner_width_cm": piece.get("clipped_corner_width_cm"),
        "clipped_corner_length_cm": piece.get("clipped_corner_length_cm"),
        "corner_mirrored": piece.get("corner_mirrored"),
        "corner_rotation_quarter_turns": piece.get("corner_rotation_quarter_turns"),
        "original_w": piece.get("original_w", piece.get("width_cm")),
        "original_h": piece.get("original_h", piece.get("length_cm")),
        "area_m2": piece.get("area_m2"),
        "exact_geometry": bool(
            isinstance(piece.get("geometry"), Mapping)
            or (
                str(piece.get("piece_type") or "") == "Special"
                and geometry_source == GEOMETRY_SOURCE_SPECIAL_JSON
            )
        ),
        "special_representation": (
            "exact_geometry"
            if geometry_source in {"persisted_dxf", GEOMETRY_SOURCE_SPECIAL_JSON}
            and str(piece.get("piece_type") or "") == "Special"
            else (
                "cnc_raw"
                if geometry_source == GEOMETRY_SOURCE_CNC_RAW
                else (
                    "unavailable"
                    if str(piece.get("piece_type") or "") == "Special"
                    else None
                )
            )
        ),
        # Geometry in the projection is already in usable-sheet orientation.
        # Never re-apply ``placement_cm.rotated`` to DXF points.
        "apply_rotated_to_geometry": False,
        "source_rotated_dims": bool(piece.get("rotated")),
        "source_orientation_applied": True,
        "allow_rotation": allow is True,
        "allow_rotation_proven": allow is not None,
        # Trusted machining parameters for draft review. Layer visibility never
        # strips these; readiness must not depend on a drawn overlay alone.
        **machining_metadata(piece),
    }


def _element(
    *,
    element_id: str,
    kind: str,
    layer_original_name: str,
    affiliation_status: str,
    sheet_no: int | None = None,
    piece_id: int | None = None,
    piece_instance_id: str | None = None,
    geometry: Any = None,
    payload: Mapping[str, Any] | None = None,
    color_source: str = COLOR_SOURCE_CATALOG_DEFAULT,
    linetype_source: str = LINETYPE_SOURCE_CATALOG_DEFAULT,
    aci_color: int | None = None,
    linetype: str | None = None,
    support_note: str | None = None,
    unit: str = GEOMETRY_UNIT,
    coordinate_space: str = GEOMETRY_COORDINATE_SPACE,
) -> dict[str, Any]:
    return {
        "element_id": element_id,
        "kind": kind,
        "layer_original_name": layer_original_name,
        "layer_match_key": layer_match_key(layer_original_name),
        "affiliation_status": affiliation_status,
        "sheet_no": sheet_no,
        "piece_id": piece_id,
        "piece_instance_id": piece_instance_id,
        "geometry": deepcopy(geometry) if geometry is not None else None,
        "payload": dict(payload or {}),
        "color_source": color_source,
        "linetype_source": linetype_source,
        "aci_color": aci_color,
        "linetype": linetype,
        "unit": unit,
        "coordinate_space": coordinate_space,
        "support_note": support_note,
    }


def _sheet_outline_element(sheet: Mapping[str, Any], *, sheet_no: int) -> dict[str, Any]:
    width_cm = sheet.get("full_width_cm")
    if width_cm is None:
        width_cm = sheet.get("w")
    length_cm = sheet.get("full_length_cm")
    if length_cm is None:
        length_cm = sheet.get("h")
    trim_w = sheet.get("applied_trim_width_cm")
    trim_l = sheet.get("applied_trim_length_cm")
    usable_w = sheet.get("usable_width_cm")
    usable_l = sheet.get("usable_length_cm")
    return _element(
        element_id=f"sheet:{sheet_no}:outline",
        kind=ELEMENT_KIND_SHEET_OUTLINE,
        layer_original_name=SHEET_OUTLINE_LAYER,
        affiliation_status=AFFILIATION_SHEET,
        sheet_no=sheet_no,
        payload={
            "full_width_cm": width_cm,
            "full_length_cm": length_cm,
            "usable_width_cm": usable_w,
            "usable_length_cm": usable_l,
            "applied_trim_width_cm": trim_w,
            "applied_trim_length_cm": trim_l,
            "resource_kind": str(sheet.get("resource_kind") or "FULL_BOARD"),
        },
        support_note=(
            "Derived from operational sheet dimensions used by export; "
            "coordinates stay usable-sheet oriented (origin top-left, y down)."
        ),
    )


def _append_outline_elements(
    elements: list[dict[str, Any]],
    *,
    token: str,
    piece: Mapping[str, Any],
    geometry: Mapping[str, Any],
    geometry_source: str,
    sheet_no: int,
    piece_id: int | None,
    instance_id: str | None,
    sheet_resource_kind: str,
    extra_payload: Mapping[str, Any] | None = None,
    support_note: str | None = None,
) -> None:
    fill_role = _fill_role_for_piece(piece, sheet_resource_kind=sheet_resource_kind)
    payload = {
        "ring": "outer",
        "apply_rotated": False,
        "geometry_source": geometry_source,
        "fill_role": fill_role,
        "display_edges": _display_edges(piece),
        "piece_type": str(piece.get("piece_type") or ""),
    }
    if extra_payload:
        payload.update(dict(extra_payload))
    elements.append(
        _element(
            element_id=f"{token}:geometry:outer",
            kind=ELEMENT_KIND_FINISHED_OUTLINE,
            layer_original_name=GEOMETRY_LAYER,
            affiliation_status=AFFILIATION_BOUND,
            sheet_no=sheet_no,
            piece_id=piece_id,
            piece_instance_id=instance_id,
            geometry=geometry,
            payload=payload,
            support_note=support_note,
        )
    )
    holes = geometry.get("holes") or []
    if isinstance(holes, list):
        for hole_index, hole in enumerate(holes):
            elements.append(
                _element(
                    element_id=f"{token}:geometry:hole:{hole_index}",
                    kind=ELEMENT_KIND_HOLE,
                    layer_original_name=GEOMETRY_LAYER,
                    affiliation_status=AFFILIATION_BOUND,
                    sheet_no=sheet_no,
                    piece_id=piece_id,
                    piece_instance_id=instance_id,
                    geometry={"path": deepcopy(hole), "closed": True},
                    payload={
                        "ring": "hole",
                        "hole_index": hole_index,
                        "apply_rotated": False,
                    },
                )
            )
    resource_kind = str(
        piece.get("resource_kind") or sheet_resource_kind or ""
    ).strip().upper()
    if resource_kind == OFFCUT_LAYER:
        elements.append(
            _element(
                element_id=f"{token}:offcut",
                kind=ELEMENT_KIND_FINISHED_OUTLINE,
                layer_original_name=OFFCUT_LAYER,
                affiliation_status=AFFILIATION_BOUND,
                sheet_no=sheet_no,
                piece_id=piece_id,
                piece_instance_id=instance_id,
                geometry=geometry,
                payload={
                    "classification": "OFFCUT",
                    "fill_role": "offcut",
                    "note": (
                        "OFFCUT remains deficient-board classification; "
                        "not a parking area for pieces outside boards."
                    ),
                },
            )
        )


def _synthetic_overlay_elements(
    piece: Mapping[str, Any],
    *,
    token: str,
    sheet_no: int,
    piece_id: int | None,
    instance_id: str | None,
    existing_kinds: set[str],
) -> list[dict[str, Any]]:
    """Derive missing machining overlays from trusted piece fields.

    Persisted DXF/snapshot overlays win. This fills the system-plan gap where
    the cutting-plan page synthesizes visual overlays client-side.
    """

    piece_type = str(piece.get("piece_type") or "")
    if piece_type == "Special":
        return []
    liner = _liner_piece_from_placed(piece)
    if liner is None:
        return []
    try:
        values = machining_values(piece)
    except (DoorLinerError, LinerGeometryError, TypeError, ValueError):
        return []

    elements: list[dict[str, Any]] = []
    synthetic_index = 0
    for addon in MACHINING_ADDONS:
        kind = addon.kind
        if kind in existing_kinds:
            continue
        spec = values.get(kind) or {}
        if not spec.get("enabled"):
            continue
        layer_name = extra_overlay_layer_for_kind(kind)
        paths: list[list[list[float]]] = []
        try:
            if kind == "liner":
                liners = list(spec.get("liners") or ())
                width_cm = float(spec.get("width_cm") or 0)
                if liners and width_cm > 0:
                    for row in liners:
                        local = liner_centerline_mm(
                            liner,
                            str(row.get("side") or ""),
                            float(row.get("offset_cm") or 0),
                            width_cm,
                            float(row.get("start_cm") or 0)
                            if row.get("start_cm") not in (None, "")
                            else None,
                            float(row.get("length_cm") or 0)
                            if row.get("length_cm") not in (None, "")
                            else None,
                        )
                        placed = _place_local_path_mm(piece, liner, local)
                        if len(placed) >= 2:
                            paths.append(placed)
                else:
                    local = liner_centerline_mm(
                        liner,
                        str(spec.get("side") or ""),
                        float(spec.get("offset_cm") or 0),
                        float(spec.get("width_cm") or 0),
                        float(spec.get("start_cm") or 0)
                        if spec.get("start_cm") not in (None, "")
                        else None,
                        float(spec.get("length_cm") or 0)
                        if spec.get("length_cm") not in (None, "")
                        else None,
                    )
                    placed = _place_local_path_mm(piece, liner, local)
                    if len(placed) >= 2:
                        paths.append(placed)
            else:
                local = liner_centerline_mm(
                    liner,
                    str(spec.get("side") or ""),
                    float(spec.get("offset_cm") or 0),
                    float(spec.get("width_cm") or 0),
                    float(spec.get("start_cm") or 0)
                    if spec.get("start_cm") not in (None, "")
                    else None,
                    float(spec.get("length_cm") or 0)
                    if spec.get("length_cm") not in (None, "")
                    else None,
                )
                placed = _place_local_path_mm(piece, liner, local)
                if len(placed) >= 2:
                    paths.append(placed)
        except (LinerGeometryError, TypeError, ValueError):
            continue

        for path in paths:
            elements.append(
                _element(
                    element_id=f"{token}:overlay-synthetic:{kind}:{synthetic_index}",
                    kind=ELEMENT_KIND_OVERLAY,
                    layer_original_name=layer_name,
                    affiliation_status=AFFILIATION_BOUND,
                    sheet_no=sheet_no,
                    piece_id=piece_id,
                    piece_instance_id=instance_id,
                    geometry=serialize_overlay_geometry_mm(
                        tuple((float(point[0]), float(point[1])) for point in path),
                        closed=False,
                    ),
                    payload={
                        "kind": kind,
                        "overlay_index": synthetic_index,
                        "apply_rotated": False,
                        "geometry_source": "parametric_visual",
                        "synthetic": True,
                    },
                )
            )
            synthetic_index += 1
        if paths:
            existing_kinds.add(kind)
    return elements


def _elements_for_piece(
    piece: Mapping[str, Any],
    *,
    sheet_no: int,
    sheet_resource_kind: str,
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    piece_id = piece_placement_id(piece)
    instance_id = str(piece.get("piece_instance_id") or "").strip() or None
    token = _stable_piece_token(piece, sheet_no=sheet_no)
    geometry = piece.get("geometry")
    piece_type = str(piece.get("piece_type") or "")

    if isinstance(geometry, Mapping):
        _append_outline_elements(
            elements,
            token=token,
            piece=piece,
            geometry=geometry,
            geometry_source="persisted_dxf",
            sheet_no=sheet_no,
            piece_id=piece_id,
            instance_id=instance_id,
            sheet_resource_kind=sheet_resource_kind,
        )
    elif piece_type == "Special":
        exact_special = _special_exact_geometry_mm(piece)
        raw_special = None if exact_special is not None else _cnc_raw_rect_geometry_mm(piece)
        if exact_special is not None:
            _append_outline_elements(
                elements,
                token=token,
                piece=piece,
                geometry=exact_special,
                geometry_source=GEOMETRY_SOURCE_SPECIAL_JSON,
                sheet_no=sheet_no,
                piece_id=piece_id,
                instance_id=instance_id,
                sheet_resource_kind=sheet_resource_kind,
                extra_payload={"special_representation": "exact_geometry"},
            )
        elif raw_special is not None:
            _append_outline_elements(
                elements,
                token=token,
                piece=piece,
                geometry=raw_special,
                geometry_source=GEOMETRY_SOURCE_CNC_RAW,
                sheet_no=sheet_no,
                piece_id=piece_id,
                instance_id=instance_id,
                sheet_resource_kind=sheet_resource_kind,
                extra_payload={
                    "special_representation": "cnc_raw",
                    "note": SUPPORT_LIMIT_SPECIAL_CNC_RAW,
                },
                support_note=SUPPORT_LIMIT_SPECIAL_CNC_RAW,
            )
        else:
            elements.append(
                _element(
                    element_id=f"{token}:geometry:unavailable",
                    kind=ELEMENT_KIND_UNRESOLVED,
                    layer_original_name=GEOMETRY_LAYER,
                    affiliation_status=AFFILIATION_BOUND if piece_id is not None else AFFILIATION_UNRESOLVED,
                    sheet_no=sheet_no,
                    piece_id=piece_id,
                    piece_instance_id=instance_id,
                    payload={
                        "reason": "special_geometry_unavailable",
                        "special_representation": "unavailable",
                        "placement_cm": {
                            "x": piece.get("x"),
                            "y": piece.get("y"),
                            "w": piece.get("w"),
                            "h": piece.get("h"),
                            "rotated": bool(piece.get("rotated")),
                        },
                        "fill_role": "special",
                    },
                    support_note=SUPPORT_LIMIT_SPECIAL_WITHOUT_GEOMETRY,
                )
            )
    else:
        parametric = _parametric_material_geometry(piece)
        if parametric is not None:
            parametric_geometry, parametric_source = parametric
            _append_outline_elements(
                elements,
                token=token,
                piece=piece,
                geometry=parametric_geometry,
                geometry_source=parametric_source,
                sheet_no=sheet_no,
                piece_id=piece_id,
                instance_id=instance_id,
                sheet_resource_kind=sheet_resource_kind,
            )
        else:
            # Fallback when parametric engines cannot derive an outline.
            elements.append(
                _element(
                    element_id=f"{token}:placement",
                    kind=ELEMENT_KIND_PLACEMENT_RECT,
                    layer_original_name=GEOMETRY_LAYER,
                    affiliation_status=AFFILIATION_BOUND,
                    sheet_no=sheet_no,
                    piece_id=piece_id,
                    piece_instance_id=instance_id,
                    payload={
                        "placement_cm": {
                            "x": piece.get("x"),
                            "y": piece.get("y"),
                            "w": piece.get("w"),
                            "h": piece.get("h"),
                            "rotated": bool(piece.get("rotated")),
                        },
                        "geometry_source": "placement_rect",
                        "fill_role": _fill_role_for_piece(
                            piece, sheet_resource_kind=sheet_resource_kind
                        ),
                        "display_edges": _display_edges(piece),
                        "apply_rotated_to_dimensions": True,
                        "note": (
                            "Axis-aligned placement from the operational plan; "
                            "rotated swaps width/height only for this rect, never for "
                            "persisted DXF outlines."
                        ),
                    },
                    unit="cm",
                    coordinate_space=GEOMETRY_COORDINATE_SPACE,
                )
            )

    existing_kinds: set[str] = set()
    overlays = piece.get("overlays")
    if isinstance(overlays, list):
        for overlay_index, overlay in enumerate(overlays):
            if not isinstance(overlay, Mapping):
                continue
            kind = str(overlay.get("kind") or "").strip()
            if kind not in EXTRA_OVERLAY_LAYER_BY_KIND:
                elements.append(
                    _element(
                        element_id=f"{token}:overlay-unresolved:{overlay_index}",
                        kind=ELEMENT_KIND_UNRESOLVED,
                        layer_original_name=str(overlay.get("layer") or ""),
                        affiliation_status=AFFILIATION_UNRESOLVED,
                        sheet_no=sheet_no,
                        piece_id=piece_id,
                        piece_instance_id=instance_id,
                        geometry=overlay.get("geometry"),
                        payload={"overlay_index": overlay_index, "kind": kind},
                        support_note="Unsupported overlay kind is not reclassified.",
                    )
                )
                continue
            existing_kinds.add(kind)
            layer_name = extra_overlay_layer_for_kind(kind)
            elements.append(
                _element(
                    element_id=f"{token}:overlay:{kind}:{overlay_index}",
                    kind=ELEMENT_KIND_OVERLAY,
                    layer_original_name=layer_name,
                    affiliation_status=AFFILIATION_BOUND,
                    sheet_no=sheet_no,
                    piece_id=piece_id,
                    piece_instance_id=instance_id,
                    geometry=overlay.get("geometry"),
                    payload={
                        "kind": kind,
                        "overlay_index": overlay_index,
                        "apply_rotated": False,
                    },
                )
            )
    # Persisted DXF overlays are physical evidence — do not re-synthesize them.
    # System/parametric pieces usually omit overlays; derive visual marks here.
    if not isinstance(geometry, Mapping):
        elements.extend(
            _synthetic_overlay_elements(
                piece,
                token=token,
                sheet_no=sheet_no,
                piece_id=piece_id,
                instance_id=instance_id,
                existing_kinds=existing_kinds,
            )
        )
    return elements


def _text_elements(
    sheet: Mapping[str, Any],
    *,
    sheet_no: int,
) -> list[dict[str, Any]]:
    labels = sheet.get("text_labels")
    if not isinstance(labels, list):
        return []
    elements: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        if not isinstance(label, Mapping):
            continue
        original_layer = str(label.get("layer") or TEXT_LAYER_EXPORT_NAME).strip()
        display_layer = (
            TEXT_LAYER_EXPORT_NAME
            if layer_match_key(original_layer)
            == layer_match_key(TEXT_LAYER_EXPORT_NAME)
            else original_layer
        )
        elements.append(
            _element(
                element_id=f"sheet:{sheet_no}:text:{index}",
                kind=ELEMENT_KIND_TEXT,
                layer_original_name=display_layer,
                affiliation_status=AFFILIATION_UNRESOLVED,
                sheet_no=sheet_no,
                payload={
                    "text": label.get("text"),
                    "x_mm": label.get("x_mm"),
                    "y_mm": label.get("y_mm"),
                    "height_mm": label.get("height_mm"),
                    "rotation_deg": label.get("rotation_deg"),
                },
                support_note=SUPPORT_LIMIT_TEXT_NOT_BOUND_BY_LAYER,
            )
        )
    return elements


def _reference_elements_from_raw(
    raw_entities: Sequence[Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project optional uploaded DXF leftovers without guessing door ownership."""

    diagnostics: list[dict[str, Any]] = []
    if not raw_entities:
        return [], diagnostics
    elements: list[dict[str, Any]] = []
    truncated = False
    for index, entity in enumerate(raw_entities):
        if not isinstance(entity, Mapping):
            continue
        if len(elements) >= MAX_REFERENCE_ENTITIES:
            truncated = True
            break
        original_layer = str(entity.get("layer") or entity.get("original_layer") or "")
        kind = str(entity.get("kind") or ELEMENT_KIND_REFERENCE)
        affiliation = AFFILIATION_REFERENCE
        if kind == ELEMENT_KIND_UNRESOLVED:
            affiliation = AFFILIATION_UNRESOLVED
        color_source = str(entity.get("color_source") or COLOR_SOURCE_BYLAYER).upper()
        if color_source not in {COLOR_SOURCE_BYLAYER, COLOR_SOURCE_BYENTITY}:
            color_source = COLOR_SOURCE_BYLAYER
        linetype_source = str(
            entity.get("linetype_source") or LINETYPE_SOURCE_BYLAYER
        ).upper()
        if linetype_source not in {
            LINETYPE_SOURCE_BYLAYER,
            LINETYPE_SOURCE_BYENTITY,
        }:
            linetype_source = LINETYPE_SOURCE_BYLAYER
        entity_id = entity.get("entity_id")
        if entity_id in (None, ""):
            element_id = f"reference:idx:{index}"
        else:
            element_id = f"reference:entity:{entity_id}"
        aci = entity.get("aci_color")
        try:
            aci_color = int(aci) if aci is not None else None
        except (TypeError, ValueError):
            aci_color = None
        elements.append(
            _element(
                element_id=element_id,
                kind=kind
                if kind
                in {
                    ELEMENT_KIND_REFERENCE,
                    ELEMENT_KIND_UNRESOLVED,
                }
                else ELEMENT_KIND_REFERENCE,
                layer_original_name=original_layer,
                affiliation_status=affiliation,
                sheet_no=entity.get("sheet_no"),
                piece_id=None,
                geometry=entity.get("geometry"),
                payload={
                    "entity_type": entity.get("entity_type"),
                    "entity_id": entity_id,
                    "reason": entity.get("reason") or "unproven_piece_affiliation",
                    "start": entity.get("start"),
                    "end": entity.get("end"),
                },
                color_source=color_source,
                linetype_source=linetype_source,
                aci_color=aci_color,
                linetype=str(entity.get("linetype") or "") or None,
                support_note=SUPPORT_LIMIT_REFERENCE_ENTITIES,
            )
        )
    if truncated:
        diagnostics.append(
            {
                "code": "REFERENCE_ENTITIES_TRUNCATED",
                "limit": MAX_REFERENCE_ENTITIES,
                "message": (
                    "Reference entity projection stopped at the safe display limit."
                ),
            }
        )
    return elements, diagnostics


def _annotate_layer_content_states(
    layers: list[dict[str, Any]],
    *,
    elements: Sequence[Mapping[str, Any]],
    layer_table: Sequence[Mapping[str, Any]] | None,
    saw_center_status: Any,
) -> list[dict[str, Any]]:
    projected_keys = {
        layer_match_key(element.get("layer_original_name"))
        for element in elements
        if element.get("layer_original_name")
    }
    occupied_in_source: set[str] = set()
    for row in layer_table or ():
        if not isinstance(row, Mapping):
            continue
        key = layer_match_key(row.get("match_key") or row.get("original_name") or row.get("name"))
        if not key:
            continue
        is_empty = bool(row.get("is_empty", row.get("is_defined_empty")))
        if not is_empty:
            occupied_in_source.add(key)

    saw_status = str(saw_center_status or "").strip()
    annotated: list[dict[str, Any]] = []
    for layer in layers:
        entry = dict(layer)
        key = layer_match_key(entry.get("match_key") or entry.get("original_name"))
        if key in projected_keys:
            entry["content_state"] = CONTENT_STATE_PROJECTED
            entry["is_defined_empty"] = False
        elif key == layer_match_key(CUT_PATH_LAYER) and saw_status in {
            "Present",
            "Legacy",
        }:
            # Manufacturing paths exist in the source contract but are not
            # synthesized for the editor read model.
            entry["content_state"] = CONTENT_STATE_UNAVAILABLE
            entry["is_defined_empty"] = False
            entry["content_note"] = SUPPORT_LIMIT_NO_CUT_PATH_GENERATION
        elif key in occupied_in_source:
            entry["content_state"] = CONTENT_STATE_UNAVAILABLE
            entry["is_defined_empty"] = False
            entry["content_note"] = (
                "Source DXF marks this layer as occupied, but its entities are "
                "not available in the editor projection."
            )
        else:
            entry["content_state"] = CONTENT_STATE_EMPTY
            entry["is_defined_empty"] = True
        annotated.append(entry)
    return annotated


def _unplaced_pieces(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = snapshot.get("unplaced")
    if not isinstance(rows, list):
        return []
    projected: list[dict[str, Any]] = []
    for piece in rows:
        if not isinstance(piece, Mapping):
            continue
        identity = _piece_identity(piece, sheet_no=None)
        identity["unplaced"] = True
        projected.append(identity)
    return projected


def project_board_editor(
    snapshot: Mapping[str, Any] | None,
    *,
    source_kind: str = "system",
    layer_table: Sequence[Mapping[str, Any]] | None = None,
    detected_layer_names: Sequence[Any] | None = None,
    reference_entities: Sequence[Mapping[str, Any]] | None = None,
    saw_center_status: str | None = None,
    default_edge_type: str = "",
) -> dict[str, Any]:
    """Project a board-editor read model from operational plan sources.

    The input snapshot object is never mutated. Financial keys are stripped from
    the snapshot and from auxiliary ``layer_table`` / ``reference_entities``.
    CUT_PATH saw centers are not synthesized here.
    """

    caller_snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    frozen_before = deepcopy(caller_snapshot)
    sanitized = sanitize_plan_snapshot(deepcopy(caller_snapshot))
    if not isinstance(sanitized, Mapping):
        sanitized = {}

    safe_layer_table = _sanitize_auxiliary(list(layer_table or []))
    if not isinstance(safe_layer_table, list):
        safe_layer_table = []
    safe_references = _sanitize_auxiliary(list(reference_entities or []))
    if not isinstance(safe_references, list):
        safe_references = []

    sheets_in = sanitized.get("sheets") if isinstance(sanitized.get("sheets"), list) else []
    projected_sheets: list[dict[str, Any]] = []
    all_elements: list[dict[str, Any]] = []
    all_pieces: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for sheet in sheets_in:
        if not isinstance(sheet, Mapping):
            continue
        try:
            sheet_no = int(sheet.get("sheet_no"))
        except (TypeError, ValueError):
            sheet_no = len(projected_sheets) + 1
        sheet_resource_kind = str(
            sheet.get("resource_kind") or "FULL_BOARD"
        ).strip().upper()
        pieces_in = sheet.get("pieces") if isinstance(sheet.get("pieces"), list) else []
        piece_rows = [piece for piece in pieces_in if isinstance(piece, Mapping)]
        piece_projections = [
            _piece_identity(piece, sheet_no=sheet_no) for piece in piece_rows
        ]
        hosting = hosting_forest_for_pieces(piece_rows)

        sheet_elements = [_sheet_outline_element(sheet, sheet_no=sheet_no)]
        for piece in piece_rows:
            sheet_elements.extend(
                _elements_for_piece(
                    piece,
                    sheet_no=sheet_no,
                    sheet_resource_kind=sheet_resource_kind,
                )
            )
        sheet_elements.extend(_text_elements(sheet, sheet_no=sheet_no))

        projected_sheets.append(
            {
                "sheet_no": sheet_no,
                "resource_kind": sheet_resource_kind or "FULL_BOARD",
                "full_width_cm": sheet.get("full_width_cm", sheet.get("w")),
                "full_length_cm": sheet.get("full_length_cm", sheet.get("h")),
                "usable_width_cm": sheet.get("usable_width_cm"),
                "usable_length_cm": sheet.get("usable_length_cm"),
                "applied_trim_width_cm": sheet.get("applied_trim_width_cm"),
                "applied_trim_length_cm": sheet.get("applied_trim_length_cm"),
                "pieces": piece_projections,
                "hosting": hosting,
                "element_ids": [row["element_id"] for row in sheet_elements],
            }
        )
        all_pieces.extend(piece_projections)
        all_elements.extend(sheet_elements)

    unplaced = _unplaced_pieces(sanitized)
    reference_elements, reference_diagnostics = _reference_elements_from_raw(
        safe_references
    )
    diagnostics.extend(reference_diagnostics)
    all_elements.extend(reference_elements)

    element_ids = [row["element_id"] for row in all_elements]
    if len(element_ids) != len(set(element_ids)):
        raise RuntimeError("board editor projection produced colliding element_id values")

    detected = list(detected_layer_names or [])
    for element in all_elements:
        detected.append(element.get("layer_original_name"))
    layers = build_layer_registry(
        layer_table=safe_layer_table,
        detected_layer_names=detected,
        include_canonical_empty=True,
    )

    status = saw_center_status
    if status is None:
        status = sanitized.get("saw_center_status")
    layers = _annotate_layer_content_states(
        layers,
        elements=all_elements,
        layer_table=safe_layer_table,
        saw_center_status=status,
    )

    legacy_physical = False
    try:
        legacy_physical = is_legacy_physical_execution_snapshot(sanitized)
    except Exception:
        legacy_physical = False

    projection = {
        "schema_version": BOARD_EDITOR_PROJECTION_SCHEMA_VERSION,
        "layer_schema_version": BOARD_EDITOR_LAYER_SCHEMA_VERSION,
        "source_kind": str(source_kind or "system"),
        "saw_center_status": status,
        "physical_execution_contract": sanitized.get(PHYSICAL_EXECUTION_CONTRACT),
        "legacy_physical_execution": legacy_physical,
        "coordinate_frame": {
            "unit": GEOMETRY_UNIT,
            "coordinate_space": GEOMETRY_COORDINATE_SPACE,
            "origin": "usable_sheet_top_left",
            "x_direction": "right",
            "y_direction": "down",
            "rtl_does_not_mirror_geometry": True,
            "placement_unit_cm": True,
            "geometry_unit_mm": True,
        },
        "edge_display": {
            # Classification baseline only. Same header the cutting-plan page
            # reads. Piece rows are not copied from a newer order.
            "default_edge_type": str(default_edge_type or "").strip(),
        },
        "board": {
            "full_width_cm": sanitized.get("full_board_width_cm"),
            "full_length_cm": sanitized.get("full_board_length_cm"),
            "usable_width_cm": sanitized.get("usable_board_width_cm"),
            "usable_length_cm": sanitized.get("usable_board_length_cm"),
            "kerf_cm": sanitized.get("kerf_cm"),
            "trim_cm": sanitized.get("trim_cm"),
        },
        "layers": layers,
        "sheets": projected_sheets,
        "pieces": all_pieces,
        "unplaced": unplaced,
        "elements": all_elements,
        "diagnostics": diagnostics,
        "view_settings": default_board_editor_view_settings(),
        "support_limits": {
            "cut_path_generation": SUPPORT_LIMIT_NO_CUT_PATH_GENERATION,
            "text_affiliation": SUPPORT_LIMIT_TEXT_NOT_BOUND_BY_LAYER,
            "reference_entities": SUPPORT_LIMIT_REFERENCE_ENTITIES,
            "historical_snapshots": SUPPORT_LIMIT_HISTORICAL_SNAPSHOT,
            "special_without_geometry": SUPPORT_LIMIT_SPECIAL_WITHOUT_GEOMETRY,
            "cut_path_entities_projected": False,
            "cut_path_layer_listed": True,
            "max_reference_entities": MAX_REFERENCE_ENTITIES,
            "affiliation_policies": {
                CUT_PATH_LAYER: AFFILIATION_MAY_SPAN_MULTIPLE_PIECES,
                TEXT_LAYER_EXPORT_NAME: AFFILIATION_NEVER_INFER_FROM_LAYER,
            },
        },
        "persistence": {
            "mutates_snapshot": False,
            "parallel_store": False,
            "stores_view_settings_in_snapshot": False,
            "writes_on_open": False,
            "generates_cut_path_on_open": False,
        },
    }

    if _nested_has_financial(projection):
        raise RuntimeError("board editor projection leaked financial keys")

    if isinstance(snapshot, Mapping) and deepcopy(snapshot) != frozen_before:
        raise RuntimeError("board editor projection mutated the input snapshot")

    return projection


__all__ = [
    "AFFILIATION_BOUND",
    "AFFILIATION_REFERENCE",
    "AFFILIATION_SHEET",
    "AFFILIATION_UNRESOLVED",
    "BOARD_EDITOR_PROJECTION_SCHEMA_VERSION",
    "CONTENT_STATE_EMPTY",
    "CONTENT_STATE_PROJECTED",
    "CONTENT_STATE_UNAVAILABLE",
    "ELEMENT_KIND_FINISHED_OUTLINE",
    "ELEMENT_KIND_HOLE",
    "ELEMENT_KIND_OVERLAY",
    "ELEMENT_KIND_PLACEMENT_RECT",
    "ELEMENT_KIND_REFERENCE",
    "ELEMENT_KIND_SHEET_OUTLINE",
    "ELEMENT_KIND_TEXT",
    "ELEMENT_KIND_UNRESOLVED",
    "MAX_REFERENCE_ENTITIES",
    "default_board_editor_view_settings",
    "project_board_editor",
]
