from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    DxfTopologyError,
    snapshot_geometry_index,
    validate_snapshot_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import layout_pair_fault
from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    dimensions_match_exact,
    special_bbox_allowed_range_cm,
    special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CATEGORY_DIMENSIONS, CATEGORY_EXPORT, CATEGORY_IDENTITY, CATEGORY_LAYOUT,
    CATEGORY_PERSISTENCE, CATEGORY_TOPOLOGY, CUT_INVALID_GEOMETRY,
    CUT_SIZE_MISMATCH, EXTRA_CUT_PATH, FORBIDDEN_ROTATION,
    KERF_VIOLATION, MANUFACTURING_REQUIREMENTS_MISSING, MATERIAL_OVERLAP,
    PIECE_COUNT_MISMATCH, PIECE_IDENTITY_MISMATCH, PIECE_INVALID_DIMENSIONS,
    PIECE_MISSING, PIECE_OUTSIDE_SHEET, PLAN_LABEL_DUPLICATE,
    PLAN_SOURCE_IDENTITY_MISMATCH, PLAN_SOURCE_MISSING, PLAN_UNPLACED_PIECES,
    PLAN_VALIDATION_FAILED,
    PLAN_UNKNOWN_PIECES, REMNANT_IDENTITY_MISMATCH, REMNANT_NOT_FOUND,
    REMNANT_REFERENCE_MISSING, SPECIAL_SIZE_MISMATCH, DxfIssueTarget, DxfValidationIssue, issue,
    pair_target, piece_target, sheet_target, topology_error_to_issue,
)
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    ManufacturingRequirementsError,
    snapshot_manufacturing_requirement_index,
)
from almdina_erp.almdina_erp.services.order_board_identity import (
    order_board_color,
    order_board_material,
    order_board_thickness_mm,
)


def _rects_overlap(a: dict[str, float], b: dict[str, float], tol: float = 1e-7) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"] + tol
        or b["x"] + b["w"] <= a["x"] + tol
        or a["y"] + a["h"] <= b["y"] + tol
        or b["y"] + b["h"] <= a["y"] + tol
    )


def _snapshot_pieces_by_sheet_id(
    snapshot: dict[str, Any],
) -> dict[tuple[int, int], dict[str, Any]]:
    indexed: dict[tuple[int, int], dict[str, Any]] = {}
    for sheet in snapshot.get("sheets") or []:
        if not isinstance(sheet, dict):
            continue
        sheet_no = cint(sheet.get("sheet_no"))
        for piece in sheet.get("pieces") or []:
            if not isinstance(piece, dict):
                continue
            piece_id = cint(piece.get("id"))
            if piece_id:
                indexed[(sheet_no, piece_id)] = piece
    return indexed


def _placed_piece_layout_row(placed: Any, stored: dict[str, Any]) -> dict[str, Any]:
    """Centimetre layout row merging child-table placement with snapshot contracts."""

    row = {
        "id": cint(placed.piece_id),
        "label": placed.piece_label or "",
        "x": flt(placed.x_mm) / 10.0,
        "y": flt(placed.y_mm) / 10.0,
        "w": flt(placed.width_mm) / 10.0,
        "h": flt(placed.height_mm) / 10.0,
        "piece_type": getattr(placed, "piece_type", None)
        or stored.get("piece_type")
        or "Regular",
        "rotated": bool(cint(getattr(placed, "rotated", 0))),
        "clipped_corner_position": (
            getattr(placed, "clipped_corner_position", None)
            or stored.get("clipped_corner_position")
            or ""
        ),
        "clipped_corner_width_cm": flt(
            getattr(placed, "clipped_corner_width_cm", None)
            if getattr(placed, "clipped_corner_width_cm", None) not in (None, "")
            else stored.get("clipped_corner_width_cm")
        ),
        "clipped_corner_length_cm": flt(
            getattr(placed, "clipped_corner_length_cm", None)
            if getattr(placed, "clipped_corner_length_cm", None) not in (None, "")
            else stored.get("clipped_corner_length_cm")
        ),
        "special_shape_geometry_json": (
            getattr(placed, "special_shape_geometry_json", None)
            or stored.get("special_shape_geometry_json")
            or ""
        ),
        "original_w": flt(
            getattr(placed, "original_width_cm", None)
            or stored.get("original_w")
            or stored.get("width_cm")
        ),
        "original_h": flt(
            getattr(placed, "original_length_cm", None)
            or stored.get("original_h")
            or stored.get("length_cm")
        ),
        "width_cm": flt(
            getattr(placed, "original_width_cm", None)
            or stored.get("original_w")
            or stored.get("width_cm")
        ),
        "length_cm": flt(
            getattr(placed, "original_length_cm", None)
            or stored.get("original_h")
            or stored.get("length_cm")
        ),
    }
    for key in ("glass_host_piece_id", "glass_hole_local_mm", "glass_margin_mm"):
        if stored.get(key) not in (None, "", []):
            row[key] = stored[key]
    return row


def _expected_snapshot_pieces(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    requirements, _ = snapshot_manufacturing_requirement_index(snapshot, require=True)
    return {
        label: {
            "width_cm": flt(piece["cut_width_cm"]),
            "length_cm": flt(piece["cut_length_cm"]),
            "allow_rotation": bool(piece["allow_rotation"]),
            "piece_type": str(piece.get("piece_type") or "Regular"),
            "source_piece_no": cint(piece["source_piece_no"]),
            "copy_no": cint(piece["copy_no"]),
        }
        for label, piece in requirements.items()
    }


def _validate_source_identity(source: Any, plan: Any, order: Any) -> list[DxfValidationIssue]:
    issues: list[DxfValidationIssue] = []
    tolerance = 0.001
    sheet_no = source.sheet_no
    target = sheet_target(int(sheet_no))

    def mismatch(code: str, field: str, expected: Any, actual: Any) -> None:
        issues.append(issue(code, CATEGORY_EXPORT, target=target, params={"field": field, "expected": expected, "actual": actual}))

    if source.board_item and getattr(plan, "board_item", None) and source.board_item != plan.board_item:
        mismatch(PLAN_SOURCE_IDENTITY_MISMATCH, "board_item", plan.board_item, source.board_item)

    expected_board = str(getattr(order, "board_description", "") or "").strip()
    source_board = str(getattr(source, "board_description", "") or "").strip()
    if expected_board and source_board and source_board != expected_board:
        mismatch(PLAN_SOURCE_IDENTITY_MISMATCH, "board_description", expected_board, source_board)

    source_material = str(getattr(source, "material", "") or "").strip()
    expected_material = str(order_board_material(order) or "").strip()
    if source_material and expected_material and source_material != expected_material:
        mismatch(PLAN_SOURCE_IDENTITY_MISMATCH, "material", expected_material, source_material)

    source_color = str(getattr(source, "color", "") or "").strip()
    expected_color = str(order_board_color(order) or "").strip()
    if source_color and expected_color and source_color != expected_color:
        mismatch(PLAN_SOURCE_IDENTITY_MISMATCH, "color", expected_color, source_color)

    source_thickness = flt(getattr(source, "thickness_mm", 0))
    expected_thickness = order_board_thickness_mm(order)
    if source_thickness and expected_thickness and abs(source_thickness - expected_thickness) > tolerance:
        mismatch(PLAN_SOURCE_IDENTITY_MISMATCH, "thickness_mm", expected_thickness, source_thickness)

    if source.source_type != "Remnant":
        return issues

    if not source.remnant:
        issues.append(issue(REMNANT_REFERENCE_MISSING, CATEGORY_EXPORT, target=target))
        return issues

    remnant = frappe.db.get_value(
        "Board Remnant",
        source.remnant,
        ["board_item", "width_mm", "length_mm", "material", "color", "thickness_mm"],
        as_dict=True,
    )
    if not remnant:
        issues.append(issue(REMNANT_NOT_FOUND, CATEGORY_EXPORT, target=target, params={"reference": source.remnant}))
        return issues

    if remnant.board_item != plan.board_item:
        mismatch(REMNANT_IDENTITY_MISMATCH, "board_item", plan.board_item, remnant.board_item)
    if (remnant.material or "") != (source.material or ""):
        mismatch(REMNANT_IDENTITY_MISMATCH, "material", source.material or "", remnant.material or "")
    if (remnant.color or "") != (source.color or ""):
        mismatch(REMNANT_IDENTITY_MISMATCH, "color", source.color or "", remnant.color or "")
    if abs(flt(remnant.thickness_mm) - flt(source.thickness_mm)) > tolerance:
        mismatch(REMNANT_IDENTITY_MISMATCH, "thickness_mm", source.thickness_mm, remnant.thickness_mm)
    if (
        abs(flt(remnant.width_mm) - flt(source.full_width_mm)) > tolerance
        or abs(flt(remnant.length_mm) - flt(source.full_length_mm)) > tolerance
    ):
        mismatch(REMNANT_IDENTITY_MISMATCH, "dimensions_mm", (source.full_width_mm, source.full_length_mm), (remnant.width_mm, remnant.length_mm))
    return issues


def validate_cutting_plan_issues(plan: Any) -> list[DxfValidationIssue]:
    issues: list[DxfValidationIssue] = []
    order = frappe.get_doc("Door Cutting Order", plan.door_cutting_order)
    source_by_sheet = {int(row.sheet_no): row for row in (plan.sources or [])}
    pieces_by_sheet: dict[int, list[Any]] = {}
    seen_labels: set[str] = set()
    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import resolved_sheet_trim_cm

    persisted_sheets = {
        int(sheet.get("sheet_no") or 0): sheet
        for sheet in (snapshot.get("sheets") or [])
        if isinstance(sheet, dict)
    }

    try:
        topology_aware = validate_snapshot_material_layout(
            snapshot,
            required_clearance_mm=flt(plan.kerf_mm),
        )
    except (DxfGeometrySnapshotError, DxfTopologyError) as exc:
        topology_aware = True
        if getattr(exc, "code", None):
            source_by_label = {
                str(piece.get("label") or piece.get("id")): piece.get("source_piece_no")
                for sheet in (snapshot.get("sheets") or [])
                for piece in (sheet.get("pieces") or [])
            }
            pair = None
            if exc.first_key is not None and exc.second_key is not None:
                first_no = source_by_label.get(str(exc.first_key))
                second_no = source_by_label.get(str(exc.second_key))
                if first_no is not None and second_no is not None and int(first_no) != int(second_no):
                    pair = (int(first_no), int(second_no))
            issues.append(topology_error_to_issue(exc, kerf_mm=flt(plan.kerf_mm), pair_identity_proven=pair is not None, pair_source_piece_nos=pair))
        else:
            issues.append(issue(CUT_INVALID_GEOMETRY, CATEGORY_TOPOLOGY, debug={"exception": repr(exc)}))

    if not source_by_sheet:
        issues.append(issue(PLAN_SOURCE_MISSING, CATEGORY_EXPORT))

    for piece in plan.placed_pieces or []:
        sheet_no = int(piece.sheet_no)
        label = piece.piece_label or ""
        if label in seen_labels:
            issues.append(issue(PLAN_LABEL_DUPLICATE, CATEGORY_IDENTITY, target=piece_target(source_piece_no=getattr(piece, "source_piece_no", None), copy_no=getattr(piece, "copy_no", None)), params={"label": label}))
        seen_labels.add(label)
        pieces_by_sheet.setdefault(sheet_no, []).append(piece)
        source = source_by_sheet.get(sheet_no)
        if not source:
            issues.append(issue(PLAN_SOURCE_MISSING, CATEGORY_EXPORT, target=sheet_target(sheet_no), params={"piece_label": label}))
            continue

        x, y = flt(piece.x_mm), flt(piece.y_mm)
        width, height = flt(piece.width_mm), flt(piece.height_mm)
        usable_w, usable_h = flt(source.usable_width_mm), flt(source.usable_length_mm)
        if width <= 0 or height <= 0:
            issues.append(issue(PIECE_INVALID_DIMENSIONS, CATEGORY_DIMENSIONS, target=piece_target(source_piece_no=getattr(piece, "source_piece_no", None), copy_no=getattr(piece, "copy_no", None)), params={"actual_width_mm": width, "actual_height_mm": height}))
        resource_kind = str(getattr(source, "resource_kind", "FULL_BOARD") or "FULL_BOARD").upper()
        if source.source_type == "Full Board" and resource_kind != "OFFCUT":
            # Placed coordinates live in the applied-trim frame. Preferred trim
            # is not a physical boundary: rebuild the same frame used by DXF
            # export, including historical missing and explicit-zero trim.
            stored = persisted_sheets.get(sheet_no) or {}
            trim_source = {
                "source_type": source.source_type,
                "full_width_cm": flt(source.full_width_mm) / 10,
                "full_length_cm": flt(source.full_length_mm) / 10,
                "usable_width_cm": usable_w / 10,
                "usable_length_cm": usable_h / 10,
                **{key: stored[key] for key in ("applied_trim_width_cm", "applied_trim_length_cm") if key in stored},
            }
            physical_x = x + resolved_sheet_trim_cm(trim_source, snapshot, axis="x") * 10
            physical_y = y + resolved_sheet_trim_cm(trim_source, snapshot, axis="y") * 10
            out_of_sheet = (
                physical_x < -1e-7 or physical_y < -1e-7
                or physical_x + width > flt(source.full_width_mm) + 1e-7
                or physical_y + height > flt(source.full_length_mm) + 1e-7
            )
        else:
            # Preserve the existing Remnant/OFFCUT usable-frame contract.
            out_of_sheet = (
                x < -1e-7 or y < -1e-7
                or x + width > usable_w + 1e-7
                or y + height > usable_h + 1e-7
            )
        if out_of_sheet:
            issues.append(issue(PIECE_OUTSIDE_SHEET, CATEGORY_LAYOUT, target=piece_target(source_piece_no=getattr(piece, "source_piece_no", None), copy_no=getattr(piece, "copy_no", None)), params={"sheet_no": sheet_no}))

    if not topology_aware:
        # System plans often lack snapshot geometry.outer/holes, so topology-aware
        # validation returns False. Reuse the shared Glass-nest layout rules with
        # snapshot piece contracts instead of treating Glass as a solid rectangle.
        kerf_cm = max(0.0, flt(plan.kerf_mm) / 10.0)
        stored_by_sheet_id = _snapshot_pieces_by_sheet_id(snapshot)
        for sheet_no, pieces in pieces_by_sheet.items():
            sheet_rows = [
                _placed_piece_layout_row(
                    piece,
                    stored_by_sheet_id.get((sheet_no, cint(piece.piece_id))) or {},
                )
                for piece in pieces
            ]
            for index, first in enumerate(pieces):
                first_row = sheet_rows[index]
                first_rect = {
                    "x": flt(first.x_mm),
                    "y": flt(first.y_mm),
                    "w": flt(first.width_mm),
                    "h": flt(first.height_mm),
                }
                for offset, second in enumerate(pieces[index + 1 :], start=index + 1):
                    second_row = sheet_rows[offset]
                    second_rect = {
                        "x": flt(second.x_mm),
                        "y": flt(second.y_mm),
                        "w": flt(second.width_mm),
                        "h": flt(second.height_mm),
                    }
                    fault = layout_pair_fault(
                        first_row,
                        second_row,
                        kerf_cm=kerf_cm,
                        sheet_pieces=sheet_rows,
                        # layout_pair_fault expects centimetres; convert mm rects.
                        first_rect={
                            "x": first_rect["x"] / 10.0,
                            "y": first_rect["y"] / 10.0,
                            "w": first_rect["w"] / 10.0,
                            "h": first_rect["h"] / 10.0,
                        },
                        second_rect={
                            "x": second_rect["x"] / 10.0,
                            "y": second_rect["y"] / 10.0,
                            "w": second_rect["w"] / 10.0,
                            "h": second_rect["h"] / 10.0,
                        },
                    )
                    if fault is None:
                        continue
                    if fault == "kerf":
                        # Kerf proximity for non-nested pairs is enforced later by
                        # export kerf validation; this gate keeps the historical
                        # MATERIAL_OVERLAP meaning for true collisions only.
                        if not _rects_overlap(first_rect, second_rect):
                            continue
                    first_no, second_no = int(first.source_piece_no), int(second.source_piece_no)
                    target = (
                        pair_target(first_no, second_no, sheet_no=sheet_no)
                        if first_no != second_no
                        else DxfIssueTarget(kind="order")
                    )
                    issues.append(issue(MATERIAL_OVERLAP, CATEGORY_LAYOUT, target=target))

    for source in plan.sources or []:
        issues.extend(_validate_source_identity(source, plan, order))

    if snapshot.get("unplaced"):
        issues.append(issue(PLAN_UNPLACED_PIECES, CATEGORY_IDENTITY))

    if (plan.plan_kind or "Order") == "Order":
        try:
            expected = _expected_snapshot_pieces(snapshot)
        except ManufacturingRequirementsError:
            issues.append(issue(MANUFACTURING_REQUIREMENTS_MISSING, CATEGORY_PERSISTENCE))
            expected = {}

        if expected:
            placed_labels = {row.piece_label for row in (plan.placed_pieces or [])}
            missing = sorted(set(expected) - placed_labels)
            extra = sorted(placed_labels - set(expected))
            if missing:
                issues.append(issue(PIECE_MISSING, CATEGORY_IDENTITY, target=DxfIssueTarget(kind="order"), params={"missing_labels": missing, "missing_count": len(missing)}))
            if extra:
                issues.append(issue(EXTRA_CUT_PATH, CATEGORY_IDENTITY, target=DxfIssueTarget(kind="order"), params={"labels": extra, "extra_count": len(extra)}))

            for piece in plan.placed_pieces or []:
                expected_piece = expected.get(piece.piece_label)
                if not expected_piece:
                    continue
                if (
                    cint(piece.source_piece_no) != expected_piece["source_piece_no"]
                    or cint(piece.copy_no) != expected_piece["copy_no"]
                ):
                    issues.append(issue(PIECE_IDENTITY_MISMATCH, CATEGORY_IDENTITY, target=piece_target(source_piece_no=cint(piece.source_piece_no), copy_no=cint(piece.copy_no))))
                width_cm = flt(piece.width_mm) / 10
                height_cm = flt(piece.height_mm) / 10
                piece_rotated = bool(cint(piece.rotated))
                if expected_piece["piece_type"] == "Special":
                    direct_match = special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction(
                        width_cm, height_cm, expected_piece["width_cm"], expected_piece["length_cm"]
                    )
                    rotated_match = special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction(
                        width_cm, height_cm, expected_piece["length_cm"], expected_piece["width_cm"]
                    )
                    dimensions_match = (rotated_match and expected_piece["allow_rotation"]) if piece_rotated else direct_match
                    forbidden_rotation_match = piece_rotated and not expected_piece["allow_rotation"] and rotated_match
                else:
                    direct_match = dimensions_match_exact(width_cm, height_cm, expected_piece["width_cm"], expected_piece["length_cm"])
                    rotated_match = dimensions_match_exact(width_cm, height_cm, expected_piece["length_cm"], expected_piece["width_cm"])
                    dimensions_match = (rotated_match and expected_piece["allow_rotation"]) if piece_rotated else direct_match
                    forbidden_rotation_match = piece_rotated and not expected_piece["allow_rotation"] and rotated_match
                if not dimensions_match and not forbidden_rotation_match:
                    target = piece_target(source_piece_no=cint(piece.source_piece_no), copy_no=cint(piece.copy_no))
                    actual_width = flt(piece.width_mm)
                    actual_height = flt(piece.height_mm)
                    dimension_code = SPECIAL_SIZE_MISMATCH if expected_piece["piece_type"] == "Special" else CUT_SIZE_MISMATCH
                    params = {
                        "actual_width_mm": actual_width,
                        "actual_height_mm": actual_height,
                        "actual_width_cm": actual_width / 10,
                        "actual_height_cm": actual_height / 10,
                        "expected_width_cm": expected_piece["width_cm"],
                        "expected_height_cm": expected_piece["length_cm"],
                    }
                    if expected_piece["piece_type"] == "Special":
                        min_w, max_w, min_h, max_h = special_bbox_allowed_range_cm(expected_piece["width_cm"], expected_piece["length_cm"])
                        params.update({
                            "allowed_min_width_cm": float(min_w),
                            "allowed_max_width_cm": float(max_w),
                            "allowed_min_height_cm": float(min_h),
                            "allowed_max_height_cm": float(max_h),
                        })
                    issues.append(issue(dimension_code, CATEGORY_DIMENSIONS, target=target, params=params))
                if cint(piece.rotated) and not expected_piece["allow_rotation"]:
                    issues.append(issue(
                        FORBIDDEN_ROTATION,
                        CATEGORY_DIMENSIONS,
                        target=piece_target(source_piece_no=cint(piece.source_piece_no), copy_no=cint(piece.copy_no)),
                        params={
                            "actual_width_mm": flt(piece.width_mm),
                            "actual_height_mm": flt(piece.height_mm),
                            "expected_width_cm": expected_piece["width_cm"],
                            "expected_height_cm": expected_piece["length_cm"],
                        },
                    ))

    return issues


def validate_cutting_plan_document(plan: Any) -> list[str]:
    """Compatibility wrapper preserving the historical list-of-strings API."""
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issues_as_strings

    return present_issues_as_strings(validate_cutting_plan_issues(plan))


def _plan_to_export_snapshot(plan: Any) -> dict[str, Any]:
    from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
        resolved_sheet_trim_cm,
    )

    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    persisted_sheets = {
        int(sheet.get("sheet_no") or 0): sheet
        for sheet in (snapshot.get("sheets") or [])
        if isinstance(sheet, dict)
    }
    geometry_by_identity, has_geometry = snapshot_geometry_index(snapshot)
    consumed_geometry: set[tuple[int, int]] = set()
    stored_pieces = {
        (int(sheet.get("sheet_no") or 0), int(piece.get("id") or 0)): piece
        for sheet in (snapshot.get("sheets") or [])
        if isinstance(sheet, dict)
        for piece in (sheet.get("pieces") or [])
        if isinstance(piece, dict)
    }
    sheets: list[dict[str, Any]] = []
    pieces_by_sheet: dict[int, list[Any]] = {}
    for piece in plan.placed_pieces or []:
        pieces_by_sheet.setdefault(int(piece.sheet_no), []).append(piece)

    for source in sorted(plan.sources or [], key=lambda row: int(row.sheet_no)):
        sheet_no = int(source.sheet_no)
        sheet_pieces: list[dict[str, Any]] = []
        for piece in pieces_by_sheet.get(sheet_no, []):
            piece_id = cint(piece.piece_id)
            public_piece = {
                "id": piece_id,
                "label": piece.piece_label,
                "piece_instance_id": getattr(piece, "piece_instance_id", "") or "",
                "resource_kind": getattr(piece, "resource_kind", "FULL_BOARD") or "FULL_BOARD",
                "offcut_source_party": getattr(piece, "offcut_source_party", "UNASSIGNED") or "UNASSIGNED",
                "offcut_execution_party": getattr(piece, "offcut_execution_party", "UNASSIGNED") or "UNASSIGNED",
                "source_piece_no": cint(piece.source_piece_no),
                "copy_no": cint(piece.copy_no),
                "x": flt(piece.x_mm) / 10,
                "y": flt(piece.y_mm) / 10,
                "w": flt(piece.width_mm) / 10,
                "h": flt(piece.height_mm) / 10,
                "original_w": flt(piece.original_width_cm),
                "original_h": flt(piece.original_length_cm),
                "piece_type": piece.piece_type or "Regular",
                "clipped_corner_position": piece.clipped_corner_position or "",
                "clipped_corner_width_cm": flt(piece.clipped_corner_width_cm),
                "clipped_corner_length_cm": flt(piece.clipped_corner_length_cm),
                "extra_liner": cint(getattr(piece, "extra_liner", 0)),
                "liner_reference_side": getattr(piece, "liner_reference_side", "") or "",
                "liner_offset_cm": flt(getattr(piece, "liner_offset_cm", 0)),
                "liner_width_cm": flt(getattr(piece, "liner_width_cm", 0)),
                "liner_start_cm": flt(getattr(piece, "liner_start_cm", 0)),
                "liner_length_cm": flt(getattr(piece, "liner_length_cm", 0)),
                "liner_specs_json": getattr(piece, "liner_specs_json", "") or "",
                "special_shape_geometry_json": (
                    getattr(piece, "special_shape_geometry_json", "") or ""
                ),
                "rotated": bool(cint(piece.rotated)),
                "edge_long_right": cint(piece.edge_long_right),
                "edge_long_left": cint(piece.edge_long_left),
                "edge_width_top": cint(piece.edge_width_top),
                "edge_width_bottom": cint(piece.edge_width_bottom),
                "edge_break": cint(getattr(piece, "edge_break", 0)),
                "edge_break_only": cint(getattr(piece, "edge_break_only", 0)),
                "edge_type": piece.edge_type or "",
                "notes": piece.notes or "",
                "area_m2": flt(piece.original_width_cm) * flt(piece.original_length_cm) / 10000,
            }
            if has_geometry:
                identity = (sheet_no, piece_id)
                geometry = geometry_by_identity.get(identity)
                if geometry is None:
                    raise DxfGeometrySnapshotError(
                        f"persisted DXF topology is missing piece identity {sheet_no}:{piece_id}."
                    )
                public_piece["geometry"] = geometry
                consumed_geometry.add(identity)
            stored = stored_pieces.get((sheet_no, piece_id)) or {}
            persisted_holes = (
                (public_piece.get("geometry") or {}).get("holes")
                if isinstance(public_piece.get("geometry"), dict)
                else None
            )
            if not persisted_holes:
                for key in ("glass_margin_mm", "glass_hole_local_mm"):
                    if stored.get(key) not in (None, "", []):
                        public_piece[key] = stored[key]
            host_id = stored.get("glass_host_piece_id")
            if host_id not in (None, ""):
                public_piece["glass_host_piece_id"] = host_id
            sheet_pieces.append(public_piece)
        persisted = persisted_sheets.get(sheet_no) or {}
        rebuilt_sheet = {
            "sheet_no": sheet_no,
            "source_type": source.source_type,
            "remnant": source.remnant,
            "board_item": source.board_item,
            "material": source.material or "",
            "color": source.color or "",
            "thickness_mm": flt(source.thickness_mm),
            "full_width_cm": flt(source.full_width_mm) / 10,
            "full_length_cm": flt(source.full_length_mm) / 10,
            "usable_width_cm": flt(source.usable_width_mm) / 10,
            "usable_length_cm": flt(source.usable_length_mm) / 10,
            "source_area_m2": flt(source.source_area_m2),
            "pieces": sheet_pieces,
        }
        for axis, key in (
            ("x", "applied_trim_width_cm"),
            ("y", "applied_trim_length_cm"),
        ):
            if key in persisted and persisted.get(key) is not None:
                rebuilt_sheet[key] = flt(persisted.get(key))
            rebuilt_sheet[key] = resolved_sheet_trim_cm(
                rebuilt_sheet,
                snapshot,
                axis=axis,
            )
        sheets.append(rebuilt_sheet)

    if has_geometry and consumed_geometry != set(geometry_by_identity):
        missing = sorted(set(geometry_by_identity) - consumed_geometry)
        raise DxfGeometrySnapshotError(
            f"persisted DXF topology contains geometry not represented by saved pieces: {missing}."
        )

    snapshot.update(
        {
            "engine_version": plan.engine_version,
            "method_key": plan.method_key,
            "method_label": plan.method_label,
            "full_board_width_cm": flt(plan.full_board_width_mm) / 10,
            "full_board_length_cm": flt(plan.full_board_length_mm) / 10,
            "usable_board_width_cm": flt(plan.usable_board_width_mm) / 10,
            "usable_board_length_cm": flt(plan.usable_board_length_mm) / 10,
            "kerf_cm": flt(plan.kerf_mm) / 10,
            "trim_cm": flt(plan.trim_margin_mm) / 10,
            "used_area_m2": flt(plan.used_area_m2),
            "total_board_area_m2": flt(plan.total_source_area_m2),
            "waste_area_m2": flt(plan.waste_area_m2),
            "required_full_boards": cint(plan.required_boards),
            "sheets": sheets,
            "unplaced": [],
            "validation": {"is_valid": True, "errors": []},
        }
    )
    return snapshot


def _strict_editable_snapshot(payload: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    payload["doctype"] = "Door Cutting Order"
    doc = frappe.get_doc(payload)
    if doc.name and not doc.is_new():
        doc.check_permission("read")
    elif not frappe.has_permission("Door Cutting Order", "create"):
        frappe.throw(
            _("You do not have permission to export an unsaved Door Cutting Order."),
            frappe.PermissionError,
        )

    if doc.status not in {None, "", "Draft", "Rejected", "Pending Review"}:
        frappe.throw(_("Approved/production DXF must come from the approved immutable Cutting Plan."))

    doc._set_piece_numbers()
    doc._validate_numeric_inputs()
    doc._validate_piece_inputs()
    doc._validate_special_shape_rows()
    doc._load_board_snapshot()
    doc._calculate_piece_rows()
    settings = doc._get_settings()
    input_fingerprint = doc._plan_input_fingerprint(settings)
    try:
        doc._calculate_cutting_plan(settings, input_fingerprint)
    except DxfTopologyError as exc:
        from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import render_error_cards_html

        frappe.throw(
            render_error_cards_html(
                [topology_error_to_issue(exc, kerf_mm=flt(getattr(doc, "kerf_mm", 0)))],
                context="export",
            ),
            title=_("تعذر تصدير DXF"),
        )
    except DxfGeometrySnapshotError as exc:
        from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import render_error_cards_html

        frappe.throw(
            render_error_cards_html(
                [issue(CUT_INVALID_GEOMETRY, CATEGORY_TOPOLOGY, debug={"exception": type(exc).__name__})],
                context="export",
            ),
            title=_("تعذر تصدير DXF"),
        )
    snapshot = frappe.parse_json(doc.cutting_plan_json or "{}") or {}
    validation = snapshot.get("validation") or {}
    validation_errors = list(validation.get("errors") or [])
    issues: list[DxfValidationIssue] = []
    legacy_validation_errors: list[str] = []
    for error in validation_errors:
        if isinstance(error, DxfValidationIssue):
            issues.append(error)
        else:
            legacy_validation_errors.append(str(error))
    if legacy_validation_errors:
        issues.append(
            issue(
                PLAN_VALIDATION_FAILED,
                CATEGORY_EXPORT,
                debug={"legacy_validation_errors": legacy_validation_errors},
            )
        )
    if snapshot.get("unplaced"):
        issues.append(issue(PLAN_UNPLACED_PIECES, CATEGORY_IDENTITY))
    if not validation.get("is_valid") and not issues:
        issues.append(issue(PLAN_VALIDATION_FAILED, CATEGORY_EXPORT))
    if issues:
        from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import render_error_cards_html

        frappe.throw(
            render_error_cards_html(issues, context="export"),
            title=_("تعذر تصدير DXF"),
        )

    return doc, _enrich_export_snapshot(snapshot, doc)


def _enrich_export_snapshot(snapshot: dict[str, Any], order: Any) -> dict[str, Any]:
    for sheet in snapshot.get("sheets") or []:
        sheet.setdefault("source_type", "Full Board")
        sheet.setdefault("remnant", None)
        sheet.setdefault("board_item", getattr(order, "board_item", None))
        sheet.setdefault("material", order_board_material(order))
        sheet.setdefault("color", order_board_color(order))
        sheet.setdefault("thickness_mm", order_board_thickness_mm(order))
        sheet.setdefault("full_width_cm", flt(snapshot.get("full_board_width_cm")))
        sheet.setdefault("full_length_cm", flt(snapshot.get("full_board_length_cm")))
        sheet.setdefault("usable_width_cm", flt(snapshot.get("usable_board_width_cm")))
        sheet.setdefault("usable_length_cm", flt(snapshot.get("usable_board_length_cm")))
        sheet.setdefault("source_area_m2", flt(sheet.get("w")) * flt(sheet.get("h")) / 10000)
    snapshot["required_full_boards"] = len(snapshot.get("sheets") or [])
    return snapshot


@frappe.whitelist()
def get_validated_dxf_plan(
    order_name: str | None = None,
    doc: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility endpoint delegated to the canonical DXF export service."""

    from almdina_erp.almdina_erp.services.dxf_export_service import (
        get_validated_dxf_plan as canonical_get_validated_dxf_plan,
    )

    return canonical_get_validated_dxf_plan(order_name=order_name, doc=doc)


__all__ = [
    "_plan_to_export_snapshot",
    "_strict_editable_snapshot",
    "get_validated_dxf_plan",
    "validate_cutting_plan_document",
]
