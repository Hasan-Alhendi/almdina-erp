"""Pure conversion of a ready board-editor draft into a Cutting Plan snapshot.

The source plan snapshot supplies identities and operational fields. The draft
layout supplies membership and pose only. Geometry is transformed once; free
rotation is baked into usable-sheet coordinates. CUT_PATH and other derived
toolpaths from the previous layout are discarded. Financial keys are never
copied from editor payloads.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    DISTRIBUTION_ACTIVE,
    DraftLayoutError,
    distribution_fingerprint,
    normalize_content_revision_token,
    normalize_layout,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
    pose_normalized_layout,
    review_saved_draft,
    trusted_model_from_projection,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import polygon_area
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    serialize_geometry_mm,
    serialize_overlay_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.dxf_text_labels import serialize_text_label
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    canonicalize_snapshot_allocation,
    decision_from_values,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import BOARD_EDITOR
from almdina_erp.almdina_erp.domain.cutting.primitives import num

METHOD_KEY = "board_editor"
METHOD_LABEL = "Board Editor"
ENGINE_VERSION = "board-editor-1"
SOLVER_STATUS = "manual_layout"

# Derived manufacturing artifacts tied to a previous placement. Never reuse them
# for a re-posed layout in this phase.
_DERIVED_PIECE_KEYS = frozenset(
    {
        "cut_path",
        "cut_paths",
        "cutter_center_path",
        "cutter_center_paths",
        "toolpath",
        "toolpaths",
        "saw_centers",
        "generated_cut_path",
        "overlays",
        "text_labels",
    }
)
_DERIVED_SHEET_KEYS = frozenset(
    {
        "cut_path",
        "cut_paths",
        "cutter_center_paths",
        "saw_centers",
        "text_labels",
        "dxf_segments",
        "dxf_entities",
        "unsupported",
        "references",
    }
)
_TOP_LEVEL_DROP = frozenset(
    {
        "cut_path",
        "cut_paths",
        "cutter_center_paths",
        "saw_centers",
        "dxf_file",
        "dxf_status",
        "generation_input_fingerprint",
        "input_fingerprint",
        "saved_layout_sha256",
        "industrial_metrics",
    }
)


class BoardEditorMaterializeError(ValueError):
    def __init__(self, code: str, *, detail: Any = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def materialize_plan_snapshot(
    *,
    draft: Mapping[str, Any],
    projection: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    machine_type: str,
    source_plan_name: str,
    expected_draft_version: int,
    source_content_revision: str,
    source_input_fingerprint: str,
) -> dict[str, Any]:
    """Build a sanitized operational snapshot for one Board Editor plan copy."""

    trusted = trusted_model_from_projection(projection, machine_type=machine_type)
    review = review_saved_draft(draft, trusted)
    if int(review.get("draft_version") or 0) != int(expected_draft_version):
        raise BoardEditorMaterializeError("version_conflict")
    if normalize_content_revision_token(str(draft.get("source_content_revision") or "")) != (
        normalize_content_revision_token(str(source_content_revision or ""))
    ):
        raise BoardEditorMaterializeError("source_changed")
    if str(draft.get("source_input_fingerprint") or "") != str(source_input_fingerprint or ""):
        raise BoardEditorMaterializeError("source_changed")
    if not review.get("ready"):
        raise BoardEditorMaterializeError("not_ready", detail=review)

    layout = draft.get("layout")
    try:
        normalized = normalize_layout(layout, _catalog_from_trusted(trusted))
    except DraftLayoutError as exc:
        raise BoardEditorMaterializeError(exc.code) from exc

    posed = pose_normalized_layout(normalized, trusted)
    if any(issue.get("severity") == "error" for issue in posed.get("issues") or []):
        raise BoardEditorMaterializeError(
            "not_ready",
            detail={
                "ready": False,
                "draft_version": int(expected_draft_version),
                "distribution_fingerprint": distribution_fingerprint(normalized),
                "issues": posed.get("issues") or [],
            },
        )

    snapshot = _build_snapshot(
        source_snapshot=source_snapshot,
        trusted=trusted,
        layout=normalized,
        posed_pieces=posed.get("pieces") or [],
        source_plan_name=source_plan_name,
        draft_version=int(expected_draft_version),
        distribution_fingerprint=distribution_fingerprint(normalized),
    )
    return snapshot


def _catalog_from_trusted(trusted: Mapping[str, Any]) -> dict[str, Any]:
    pieces = {}
    for instance, info in (trusted.get("pieces") or {}).items():
        pieces[str(instance)] = {
            "piece_id": info.get("piece_id"),
            "allow_rotation": info.get("allow_rotation") is True
            and info.get("allow_rotation_proven") is True,
            "glass_host_piece_id": info.get("glass_host_piece_id"),
        }
    return {
        "pieces": pieces,
        "source_sheet_nos": [int(number) for number in (trusted.get("sheets") or {})],
    }


def _build_snapshot(
    *,
    source_snapshot: Mapping[str, Any],
    trusted: Mapping[str, Any],
    layout: Mapping[str, Any],
    posed_pieces: Sequence[Mapping[str, Any]],
    source_plan_name: str,
    draft_version: int,
    distribution_fingerprint: str,
) -> dict[str, Any]:
    source_index = _index_source_pieces(source_snapshot)
    source_sheets = {
        int(sheet.get("sheet_no") or 0): sheet
        for sheet in (source_snapshot.get("sheets") or [])
        if int(sheet.get("sheet_no") or 0) > 0
    }
    kept_boards = {int(board["sheet_no"]) for board in layout.get("boards") or []}
    active = [
        piece
        for piece in posed_pieces
        if piece.get("distribution") == DISTRIBUTION_ACTIVE
        and piece.get("sheet_no") not in (None, "")
        and int(piece.get("sheet_no") or 0) in kept_boards
    ]

    by_sheet: dict[int, list[dict[str, Any]]] = {number: [] for number in sorted(kept_boards)}
    for posed in active:
        sheet_no = int(posed["sheet_no"])
        by_sheet.setdefault(sheet_no, []).append(
            _materialize_piece(
                posed=posed,
                source_piece=source_index.get(str(posed.get("piece_instance_id") or "")),
                trusted_piece=(trusted.get("pieces") or {}).get(str(posed.get("piece_instance_id") or "")),
            )
        )

    sheets: list[dict[str, Any]] = []
    used_area = 0.0
    total_board_area = 0.0
    for sheet_no in sorted(by_sheet):
        trusted_sheet = (trusted.get("sheets") or {}).get(str(sheet_no)) or {}
        source_sheet = source_sheets.get(sheet_no) or {}
        sheet = _materialize_sheet(
            sheet_no=sheet_no,
            trusted_sheet=trusted_sheet,
            source_sheet=source_sheet,
            pieces=by_sheet[sheet_no],
            source_snapshot=source_snapshot,
        )
        sheets.append(sheet)
        used_area += sum(num(piece.get("area_m2")) for piece in sheet.get("pieces") or [])
        total_board_area += num(sheet.get("source_area_m2"))

    snapshot = {
        key: deepcopy(value)
        for key, value in source_snapshot.items()
        if key not in _TOP_LEVEL_DROP and key != "sheets"
    }
    snapshot["sheets"] = sheets
    snapshot["unplaced"] = []
    snapshot["method_key"] = METHOD_KEY
    snapshot["method_label"] = METHOD_LABEL
    snapshot["engine_version"] = ENGINE_VERSION
    snapshot["solver_status"] = SOLVER_STATUS
    snapshot["ordering_strategy"] = "board_editor_manual"
    snapshot["attempts"] = 0
    snapshot["score"] = None
    snapshot["search_elapsed_sec"] = 0
    snapshot["used_area_m2"] = used_area
    snapshot["total_board_area_m2"] = total_board_area
    snapshot["waste_area_m2"] = max(0.0, total_board_area - used_area)
    snapshot["saw_center_status"] = "Absent"
    snapshot["validation"] = {"is_valid": True, "errors": []}
    snapshot["layout_origin"] = {
        "kind": BOARD_EDITOR,
        "source_plan": str(source_plan_name or ""),
        "draft_version": int(draft_version),
        "distribution_fingerprint": str(distribution_fingerprint or ""),
        "dxf_file_bound": False,
        "cut_path_carried": False,
    }
    snapshot["industrial_metrics"] = {
        "estimated_cut_count": 0,
        "estimated_cut_length_cm": 0,
        "largest_reusable_free_area_m2": 0,
        "rotation_count": sum(
            1
            for piece in active
            if abs(num(piece.get("rotation_deg"))) > 1e-6
        ),
    }
    return canonicalize_snapshot_allocation(snapshot)


def _index_source_pieces(source_snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for sheet in source_snapshot.get("sheets") or []:
        if not isinstance(sheet, Mapping):
            continue
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, Mapping):
                continue
            instance = str(piece.get("piece_instance_id") or "").strip()
            if instance and instance not in indexed:
                indexed[instance] = dict(piece)
    return indexed


def _materialize_sheet(
    *,
    sheet_no: int,
    trusted_sheet: Mapping[str, Any],
    source_sheet: Mapping[str, Any],
    pieces: list[dict[str, Any]],
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    decision = decision_from_values(
        trusted_sheet.get("resource_kind") or source_sheet.get("resource_kind"),
        trusted_sheet.get("offcut_source_party") or source_sheet.get("offcut_source_party"),
        trusted_sheet.get("offcut_execution_party") or source_sheet.get("offcut_execution_party"),
    )
    usable_w = num(trusted_sheet.get("usable_width_mm"))
    usable_h = num(trusted_sheet.get("usable_length_mm"))
    if usable_w <= 0:
        usable_w = num(source_sheet.get("usable_width_cm") or source_sheet.get("w")) * 10.0
    if usable_h <= 0:
        usable_h = num(source_sheet.get("usable_length_cm") or source_sheet.get("h")) * 10.0
    full_w = num(source_sheet.get("full_width_cm")) * 10.0 or num(
        source_snapshot.get("full_board_width_cm")
    ) * 10.0 or usable_w
    full_h = num(source_sheet.get("full_length_cm")) * 10.0 or num(
        source_snapshot.get("full_board_length_cm")
    ) * 10.0 or usable_h
    source_area = usable_w * usable_h / 1_000_000.0
    used_area = sum(num(piece.get("area_m2")) for piece in pieces)
    sheet: dict[str, Any] = {
        key: deepcopy(value)
        for key, value in source_sheet.items()
        if key not in _DERIVED_SHEET_KEYS and key != "pieces"
    }
    sheet.update(
        {
            "sheet_no": sheet_no,
            "resource_kind": decision.resource_kind.value,
            "offcut_source_party": decision.source_party.value,
            "offcut_execution_party": decision.execution_party.value,
            "w": usable_w / 10.0,
            "h": usable_h / 10.0,
            "usable_width_cm": usable_w / 10.0,
            "usable_length_cm": usable_h / 10.0,
            "full_width_cm": full_w / 10.0,
            "full_length_cm": full_h / 10.0,
            "source_area_m2": source_area,
            "used_area_m2": used_area,
            "waste_area_m2": max(0.0, source_area - used_area),
            "pieces": pieces,
            "text_labels": _labels_for_pieces(pieces),
            "dxf_file_bound": False,
        }
    )
    return sheet


def _materialize_piece(
    *,
    posed: Mapping[str, Any],
    source_piece: Mapping[str, Any] | None,
    trusted_piece: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source = dict(source_piece or {})
    for key in _DERIVED_PIECE_KEYS:
        source.pop(key, None)
    trusted = trusted_piece or {}
    width_mm = num(trusted.get("width_mm"))
    length_mm = num(trusted.get("length_mm"))
    if width_mm <= 0:
        width_mm = num(source.get("w")) * 10.0
    if length_mm <= 0:
        length_mm = num(source.get("h")) * 10.0
    original_w = trusted.get("original_w")
    original_h = trusted.get("original_h")
    if original_w is None:
        original_w = source.get("original_w", width_mm / 10.0)
    if original_h is None:
        original_h = source.get("original_h", length_mm / 10.0)

    outline = posed.get("outline_mm")
    holes = []
    hole = posed.get("glass_hole_local_mm")
    if isinstance(hole, list) and len(hole) >= 3:
        holes.append(hole)
    piece_type = str(trusted.get("piece_type") or source.get("piece_type") or "")
    geometry_source = str(
        trusted.get("geometry_source") or source.get("geometry_source") or ""
    )
    exact_geometry = bool(trusted.get("exact_geometry") or source.get("exact_geometry"))
    source_geometry = (
        source.get("geometry") if isinstance(source.get("geometry"), Mapping) else None
    )
    # Never promote CNC-raw stock rectangles (or blank Special JSON) into a
    # persisted DXF ``geometry`` contour. Exact DXF source keeps posed outline.
    promote_outline = False
    if source_geometry is not None and isinstance(outline, list) and len(outline) >= 3:
        promote_outline = True
    elif piece_type == "Special":
        promote_outline = False
    elif isinstance(outline, list) and len(outline) >= 3:
        promote_outline = True

    geometry = None
    if promote_outline:
        geometry = serialize_geometry_mm(
            PartGeometry(
                outer=tuple((num(p[0]), num(p[1])) for p in outline),
                holes=tuple(
                    tuple((num(p[0]), num(p[1])) for p in ring)
                    for ring in holes
                ),
            )
        )
    area_m2 = _area_m2(outline, holes)
    if area_m2 <= 0:
        area_m2 = abs(width_mm * length_mm) / 1_000_000.0

    piece = {
        **source,
        "piece_instance_id": str(posed.get("piece_instance_id") or source.get("piece_instance_id") or ""),
        "id": posed.get("piece_id") if posed.get("piece_id") is not None else source.get("id"),
        "label": posed.get("label") or source.get("label") or posed.get("piece_instance_id"),
        "x": num(posed.get("local_x_mm")) / 10.0,
        "y": num(posed.get("local_y_mm")) / 10.0,
        # Physical cut dims stay entry/source dims — never the post-rotation AABB.
        "w": width_mm / 10.0,
        "h": length_mm / 10.0,
        "original_w": num(original_w),
        "original_h": num(original_h),
        "rotated": False,
        "rotation_deg": num(posed.get("rotation_deg")),
        "apply_rotated_to_geometry": False,
        "area_m2": area_m2,
        "glass_host_piece_id": posed.get("glass_host_piece_id"),
        "resource_kind": posed.get("resource_kind") or source.get("resource_kind"),
        "offcut_source_party": posed.get("offcut_source_party") or source.get("offcut_source_party"),
        "offcut_execution_party": posed.get("offcut_execution_party")
        or source.get("offcut_execution_party"),
        "overlays": _overlays_from_machining(posed.get("machining_paths") or []),
        "piece_type": piece_type or source.get("piece_type") or "Regular",
    }
    if geometry is not None:
        piece["geometry"] = geometry
    else:
        piece.pop("geometry", None)
    # Preserve manufacturing Special contracts from source; layout pose is x/y/w/h.
    if piece_type == "Special":
        if source.get("special_shape_geometry_json") not in (None, ""):
            piece["special_shape_geometry_json"] = source.get("special_shape_geometry_json")
        if geometry_source == "cnc_raw_rect" or (
            not exact_geometry and not source_geometry and not source.get("special_shape_geometry_json")
        ):
            piece.pop("geometry", None)
    return piece


def _overlays_from_machining(paths: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    for item in paths:
        if not isinstance(item, Mapping):
            continue
        path = item.get("path_mm")
        if not isinstance(path, list) or len(path) < 2:
            continue
        points = [(num(point[0]), num(point[1])) for point in path if isinstance(point, Sequence)]
        if len(points) < 2:
            continue
        kind = str(item.get("kind") or item.get("addon_kind") or "machining")
        overlays.append(
            {
                "kind": kind,
                "layer": str(item.get("layer") or kind),
                "geometry": serialize_overlay_geometry_mm(
                    points,
                    closed=bool(item.get("closed")),
                ),
            }
        )
    return overlays


def _labels_for_pieces(pieces: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for piece in pieces:
        text = str(piece.get("label") or "").strip()
        if not text:
            continue
        geometry = piece.get("geometry") if isinstance(piece.get("geometry"), Mapping) else None
        outer = geometry.get("outer") if geometry else None
        if isinstance(outer, list) and len(outer) >= 3:
            xs = [num(point[0]) for point in outer]
            ys = [num(point[1]) for point in outer]
        else:
            # CNC-raw Special has no persisted DXF geometry; label from placement.
            x = num(piece.get("x")) * 10.0
            y = num(piece.get("y")) * 10.0
            w = num(piece.get("w")) * 10.0
            h = num(piece.get("h")) * 10.0
            if not (w > 0 and h > 0):
                continue
            xs = [x, x + w]
            ys = [y, y + h]
        try:
            labels.append(
                serialize_text_label(
                    text=text,
                    x_mm=(min(xs) + max(xs)) * 0.5,
                    y_mm=(min(ys) + max(ys)) * 0.5,
                    height_mm=max(8.0, min(num(piece.get("h")) * 10.0 * 0.08, 40.0)),
                    rotation_deg=num(piece.get("rotation_deg")),
                )
            )
        except ValueError:
            continue
    return labels


def _area_m2(outline: Any, holes: Sequence[Any]) -> float:
    if not isinstance(outline, list) or len(outline) < 3:
        return 0.0
    outer = polygon_area([(num(p[0]), num(p[1])) for p in outline])
    hole_area = 0.0
    for hole in holes:
        if isinstance(hole, list) and len(hole) >= 3:
            hole_area += polygon_area([(num(p[0]), num(p[1])) for p in hole])
    return max(0.0, (outer - hole_area) / 1_000_000.0)


__all__ = [
    "BOARD_EDITOR",
    "BoardEditorMaterializeError",
    "ENGINE_VERSION",
    "METHOD_KEY",
    "METHOD_LABEL",
    "materialize_plan_snapshot",
]
