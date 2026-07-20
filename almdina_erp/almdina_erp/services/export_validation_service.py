from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt


def _rects_overlap(a: dict[str, float], b: dict[str, float], tol: float = 1e-7) -> bool:
    return not (
        a["x"] + a["w"] <= b["x"] + tol
        or b["x"] + b["w"] <= a["x"] + tol
        or a["y"] + a["h"] <= b["y"] + tol
        or b["y"] + b["h"] <= a["y"] + tol
    )


def _expected_order_pieces(order: Any) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    for group_index, row in enumerate(order.pieces or [], start=1):
        for copy_no in range(1, cint(row.qty) + 1):
            expected[f"{group_index}.{copy_no}"] = {
                "width_cm": flt(row.width_cm),
                "length_cm": flt(row.length_cm),
                "allow_rotation": cint(row.allow_rotation),
            }
    return expected


def validate_cutting_plan_document(plan: Any) -> list[str]:
    errors: list[str] = []
    source_by_sheet = {int(row.sheet_no): row for row in (plan.sources or [])}
    pieces_by_sheet: dict[int, list[Any]] = {}
    seen_labels: set[str] = set()

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

        x = flt(piece.x_mm)
        y = flt(piece.y_mm)
        width = flt(piece.width_mm)
        height = flt(piece.height_mm)
        usable_w = flt(source.usable_width_mm)
        usable_h = flt(source.usable_length_mm)
        if width <= 0 or height <= 0:
            errors.append(_("Piece {0} has invalid dimensions.").format(label))
        if x < -1e-7 or y < -1e-7 or x + width > usable_w + 1e-7 or y + height > usable_h + 1e-7:
            errors.append(_("Piece {0} exceeds source sheet {1} bounds.").format(label, sheet_no))

    for sheet_no, pieces in pieces_by_sheet.items():
        for index, first in enumerate(pieces):
            a = {"x": flt(first.x_mm), "y": flt(first.y_mm), "w": flt(first.width_mm), "h": flt(first.height_mm)}
            for second in pieces[index + 1:]:
                b = {"x": flt(second.x_mm), "y": flt(second.y_mm), "w": flt(second.width_mm), "h": flt(second.height_mm)}
                if _rects_overlap(a, b):
                    errors.append(
                        _("Pieces {0} and {1} overlap on source sheet {2}.").format(
                            first.piece_label, second.piece_label, sheet_no
                        )
                    )

    for source in plan.sources or []:
        if source.board_item and source.board_item != plan.board_item:
            errors.append(_("Source sheet {0} uses a different Board Item.").format(source.sheet_no))
        if source.source_type == "Remnant":
            if not source.remnant:
                errors.append(_("Remnant source sheet {0} has no Board Remnant reference.").format(source.sheet_no))
            else:
                remnant = frappe.db.get_value(
                    "Board Remnant",
                    source.remnant,
                    ["board_item", "width_mm", "length_mm"],
                    as_dict=True,
                )
                if not remnant:
                    errors.append(_("Board Remnant {0} no longer exists.").format(source.remnant))
                else:
                    if remnant.board_item != plan.board_item:
                        errors.append(_("Board Remnant {0} does not match the plan Board Item.").format(source.remnant))
                    if abs(flt(remnant.width_mm) - flt(source.full_width_mm)) > 0.001 or abs(flt(remnant.length_mm) - flt(source.full_length_mm)) > 0.001:
                        errors.append(_("Board Remnant {0} dimensions differ from the approved source snapshot.").format(source.remnant))

    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    if snapshot.get("unplaced"):
        errors.append(_("Cutting Plan contains unplaced pieces."))

    if (plan.plan_kind or "Order") == "Order":
        order = frappe.get_doc("Door Cutting Order", plan.door_cutting_order)
        expected = _expected_order_pieces(order)
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
            width_cm = flt(piece.width_mm) / 10
            height_cm = flt(piece.height_mm) / 10
            normal = abs(width_cm - expected_piece["width_cm"]) <= 0.001 and abs(height_cm - expected_piece["length_cm"]) <= 0.001
            rotated = (
                expected_piece["allow_rotation"]
                and abs(width_cm - expected_piece["length_cm"]) <= 0.001
                and abs(height_cm - expected_piece["width_cm"]) <= 0.001
            )
            if not (normal or rotated):
                errors.append(_("Piece {0} dimensions/orientation do not match the order request.").format(piece.piece_label))
            if cint(piece.rotated) and not expected_piece["allow_rotation"]:
                errors.append(_("Piece {0} is rotated without permission.").format(piece.piece_label))

    return errors


def _plan_to_export_snapshot(plan: Any) -> dict[str, Any]:
    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    sheets: list[dict[str, Any]] = []
    pieces_by_sheet: dict[int, list[Any]] = {}
    for piece in plan.placed_pieces or []:
        pieces_by_sheet.setdefault(int(piece.sheet_no), []).append(piece)

    for source in sorted(plan.sources or [], key=lambda row: int(row.sheet_no)):
        sheet_pieces: list[dict[str, Any]] = []
        for piece in pieces_by_sheet.get(int(source.sheet_no), []):
            sheet_pieces.append(
                {
                    "id": cint(piece.piece_id),
                    "label": piece.piece_label,
                    "source_piece_no": cint(piece.source_piece_no),
                    "copy_no": cint(piece.copy_no),
                    "x": flt(piece.x_mm) / 10,
                    "y": flt(piece.y_mm) / 10,
                    "w": flt(piece.width_mm) / 10,
                    "h": flt(piece.height_mm) / 10,
                    "original_w": flt(piece.original_width_cm),
                    "original_h": flt(piece.original_length_cm),
                    "rotated": bool(cint(piece.rotated)),
                    "edge_long_right": cint(piece.edge_long_right),
                    "edge_long_left": cint(piece.edge_long_left),
                    "edge_width_top": cint(piece.edge_width_top),
                    "edge_width_bottom": cint(piece.edge_width_bottom),
                    "edge_type": piece.edge_type or "",
                    "notes": piece.notes or "",
                    "area_m2": flt(piece.original_width_cm) * flt(piece.original_length_cm) / 10000,
                }
            )
        sheets.append(
            {
                "sheet_no": int(source.sheet_no),
                "source_type": source.source_type,
                "remnant": source.remnant,
                "board_item": source.board_item,
                "full_width_cm": flt(source.full_width_mm) / 10,
                "full_length_cm": flt(source.full_length_mm) / 10,
                "usable_width_cm": flt(source.usable_width_mm) / 10,
                "usable_length_cm": flt(source.usable_length_mm) / 10,
                "source_area_m2": flt(source.source_area_m2),
                "pieces": sheet_pieces,
            }
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


@frappe.whitelist()
def get_validated_dxf_plan(order_name: str) -> dict[str, Any]:
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    if not order.approved_plan:
        frappe.throw(_("Save and approve the order before exporting a production DXF."))

    plan = frappe.get_doc("Cutting Plan", order.approved_plan)
    errors = validate_cutting_plan_document(plan)
    if errors:
        frappe.throw(_("DXF export blocked by geometry validation:\n{0}").format("\n".join(errors)))

    snapshot = _plan_to_export_snapshot(plan)
    manifest = {
        "order": order.name,
        "customer": order.customer,
        "revision": cint(plan.revision),
        "cutting_plan": plan.name,
        "plan_kind": plan.plan_kind or "Order",
        "units": "mm",
        "engine_version": plan.engine_version,
        "method_key": plan.method_key,
        "method_label": plan.method_label,
        "sheet_count": len(plan.sources or []),
        "sources": [
            {
                "sheet_no": int(row.sheet_no),
                "source_type": row.source_type,
                "remnant": row.remnant,
                "board_item": row.board_item,
                "full_width_mm": flt(row.full_width_mm),
                "full_length_mm": flt(row.full_length_mm),
                "usable_width_mm": flt(row.usable_width_mm),
                "usable_length_mm": flt(row.usable_length_mm),
            }
            for row in (plan.sources or [])
        ],
    }
    return {"plan": snapshot, "manifest": manifest}
