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


def _expected_snapshot_pieces(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    requirements, _ = snapshot_manufacturing_requirement_index(snapshot, require=True)
    return {
        label: {
            "width_cm": flt(piece["cut_width_cm"]),
            "length_cm": flt(piece["cut_length_cm"]),
            "allow_rotation": bool(piece["allow_rotation"]),
            "source_piece_no": cint(piece["source_piece_no"]),
            "copy_no": cint(piece["copy_no"]),
        }
        for label, piece in requirements.items()
    }


def _validate_source_identity(source: Any, plan: Any, order: Any, errors: list[str]) -> None:
    tolerance = 0.001
    sheet_no = source.sheet_no

    if source.board_item and getattr(plan, "board_item", None) and source.board_item != plan.board_item:
        errors.append(_("Source sheet {0} uses a different Board Item.").format(sheet_no))

    expected_board = str(getattr(order, "board_description", "") or "").strip()
    source_board = str(getattr(source, "board_description", "") or "").strip()
    if expected_board and source_board and source_board != expected_board:
        errors.append(
            _("Source sheet {0} board description does not match the order snapshot.").format(sheet_no)
        )

    source_material = str(getattr(source, "material", "") or "").strip()
    expected_material = str(order_board_material(order) or "").strip()
    if source_material and expected_material and source_material != expected_material:
        errors.append(_("Source sheet {0} material does not match the order snapshot.").format(sheet_no))

    source_color = str(getattr(source, "color", "") or "").strip()
    expected_color = str(order_board_color(order) or "").strip()
    if source_color and expected_color and source_color != expected_color:
        errors.append(_("Source sheet {0} color does not match the order snapshot.").format(sheet_no))

    source_thickness = flt(getattr(source, "thickness_mm", 0))
    expected_thickness = order_board_thickness_mm(order)
    if source_thickness and expected_thickness and abs(source_thickness - expected_thickness) > tolerance:
        errors.append(_("Source sheet {0} thickness does not match the order snapshot.").format(sheet_no))

    if source.source_type != "Remnant":
        return

    if not source.remnant:
        errors.append(_("Remnant source sheet {0} has no Board Remnant reference.").format(sheet_no))
        return

    remnant = frappe.db.get_value(
        "Board Remnant",
        source.remnant,
        ["board_item", "width_mm", "length_mm", "material", "color", "thickness_mm"],
        as_dict=True,
    )
    if not remnant:
        errors.append(_("Board Remnant {0} no longer exists.").format(source.remnant))
        return

    if remnant.board_item != plan.board_item:
        errors.append(_("Board Remnant {0} does not match the plan Board Item.").format(source.remnant))
    if (remnant.material or "") != (source.material or ""):
        errors.append(
            _("Board Remnant {0} material differs from the approved source snapshot.").format(
                source.remnant
            )
        )
    if (remnant.color or "") != (source.color or ""):
        errors.append(
            _("Board Remnant {0} color differs from the approved source snapshot.").format(
                source.remnant
            )
        )
    if abs(flt(remnant.thickness_mm) - flt(source.thickness_mm)) > tolerance:
        errors.append(
            _("Board Remnant {0} thickness differs from the approved source snapshot.").format(
                source.remnant
            )
        )
    if (
        abs(flt(remnant.width_mm) - flt(source.full_width_mm)) > tolerance
        or abs(flt(remnant.length_mm) - flt(source.full_length_mm)) > tolerance
    ):
        errors.append(
            _("Board Remnant {0} dimensions differ from the approved source snapshot.").format(
                source.remnant
            )
        )


def _topology_validation_error(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if code:
        first = getattr(exc, "first_key", None) or "?"
        second = getattr(exc, "second_key", None) or "?"
        return _("Persisted DXF topology validation failed ({0}) between pieces {1} and {2}.").format(
            code,
            first,
            second,
        )
    return _("Persisted DXF topology is invalid: {0}").format(str(exc))


def validate_cutting_plan_document(plan: Any) -> list[str]:
    errors: list[str] = []
    order = frappe.get_doc("Door Cutting Order", plan.door_cutting_order)
    source_by_sheet = {int(row.sheet_no): row for row in (plan.sources or [])}
    pieces_by_sheet: dict[int, list[Any]] = {}
    seen_labels: set[str] = set()
    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}

    try:
        topology_aware = validate_snapshot_material_layout(
            snapshot,
            required_clearance_mm=flt(plan.kerf_mm),
        )
    except (DxfGeometrySnapshotError, DxfTopologyError) as exc:
        topology_aware = True
        errors.append(_topology_validation_error(exc))

    if not source_by_sheet:
        errors.append(_("Cutting Plan has no physical sources."))

    for piece in plan.placed_pieces or []:
        sheet_no = int(piece.sheet_no)
        label = piece.piece_label or ""
        if label in seen_labels:
            errors.append(_("Piece label {0} is duplicated in the Cutting Plan.").format(label))
        seen_labels.add(label)
        pieces_by_sheet.setdefault(sheet_no, []).append(piece)
        source = source_by_sheet.get(sheet_no)
        if not source:
            errors.append(_("Piece {0} references missing source sheet {1}.").format(label, sheet_no))
            continue

        x, y = flt(piece.x_mm), flt(piece.y_mm)
        width, height = flt(piece.width_mm), flt(piece.height_mm)
        usable_w, usable_h = flt(source.usable_width_mm), flt(source.usable_length_mm)
        if width <= 0 or height <= 0:
            errors.append(_("Piece {0} has invalid dimensions.").format(label))
        if x < -1e-7 or y < -1e-7 or x + width > usable_w + 1e-7 or y + height > usable_h + 1e-7:
            errors.append(_("Piece {0} exceeds source sheet {1} bounds.").format(label, sheet_no))

    if not topology_aware:
        for sheet_no, pieces in pieces_by_sheet.items():
            for index, first in enumerate(pieces):
                first_rect = {
                    "x": flt(first.x_mm),
                    "y": flt(first.y_mm),
                    "w": flt(first.width_mm),
                    "h": flt(first.height_mm),
                }
                for second in pieces[index + 1 :]:
                    second_rect = {
                        "x": flt(second.x_mm),
                        "y": flt(second.y_mm),
                        "w": flt(second.width_mm),
                        "h": flt(second.height_mm),
                    }
                    if _rects_overlap(first_rect, second_rect):
                        errors.append(
                            _("Pieces {0} and {1} overlap on source sheet {2}.").format(
                                first.piece_label,
                                second.piece_label,
                                sheet_no,
                            )
                        )

    for source in plan.sources or []:
        _validate_source_identity(source, plan, order, errors)

    if snapshot.get("unplaced"):
        errors.append(_("Cutting Plan contains unplaced pieces."))

    if (plan.plan_kind or "Order") == "Order":
        try:
            expected = _expected_snapshot_pieces(snapshot)
        except ManufacturingRequirementsError:
            errors.append(
                _(
                    "Saved Cutting Plan has no valid captured manufacturing requirements. "
                    "Recalculate the plan or re-import the DXF before manufacturing/export."
                )
            )
            expected = {}

        if expected:
            placed_labels = {row.piece_label for row in (plan.placed_pieces or [])}
            missing = sorted(set(expected) - placed_labels)
            extra = sorted(placed_labels - set(expected))
            if missing:
                errors.append(_("Cutting Plan is missing required pieces: {0}").format(", ".join(missing)))
            if extra:
                errors.append(_("Cutting Plan contains unknown pieces: {0}").format(", ".join(extra)))

            for piece in plan.placed_pieces or []:
                expected_piece = expected.get(piece.piece_label)
                if not expected_piece:
                    continue
                if (
                    cint(piece.source_piece_no) != expected_piece["source_piece_no"]
                    or cint(piece.copy_no) != expected_piece["copy_no"]
                ):
                    errors.append(
                        _("Piece {0} identity does not match the captured manufacturing request.").format(
                            piece.piece_label
                        )
                    )
                width_cm = flt(piece.width_mm) / 10
                height_cm = flt(piece.height_mm) / 10
                normal = (
                    abs(width_cm - expected_piece["width_cm"]) <= 0.001
                    and abs(height_cm - expected_piece["length_cm"]) <= 0.001
                )
                rotated = (
                    expected_piece["allow_rotation"]
                    and abs(width_cm - expected_piece["length_cm"]) <= 0.001
                    and abs(height_cm - expected_piece["width_cm"]) <= 0.001
                )
                if not (normal or rotated):
                    errors.append(
                        _("Piece {0} dimensions/orientation do not match the captured manufacturing request.").format(
                            piece.piece_label
                        )
                    )
                if cint(piece.rotated) and not expected_piece["allow_rotation"]:
                    errors.append(_("Piece {0} is rotated without permission.").format(piece.piece_label))

    return errors


def _plan_to_export_snapshot(plan: Any) -> dict[str, Any]:
    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    geometry_by_identity, has_geometry = snapshot_geometry_index(snapshot)
    consumed_geometry: set[tuple[int, int]] = set()
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
                "special_shape_geometry_json": (
                    getattr(piece, "special_shape_geometry_json", "") or ""
                ),
                "rotated": bool(cint(piece.rotated)),
                "edge_long_right": cint(piece.edge_long_right),
                "edge_long_left": cint(piece.edge_long_left),
                "edge_width_top": cint(piece.edge_width_top),
                "edge_width_bottom": cint(piece.edge_width_bottom),
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
            sheet_pieces.append(public_piece)
        sheets.append(
            {
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
        )

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
    doc._calculate_cutting_plan(settings, input_fingerprint)
    snapshot = frappe.parse_json(doc.cutting_plan_json or "{}") or {}
    validation = snapshot.get("validation") or {}
    errors = list(validation.get("errors") or [])
    if snapshot.get("unplaced"):
        errors.append(_("Cutting Plan contains unplaced pieces."))
    if not validation.get("is_valid") or errors:
        frappe.throw(_("DXF export blocked by geometry validation:\n{0}").format("\n".join(errors)))

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
