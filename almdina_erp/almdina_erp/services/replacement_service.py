from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


ENGINE_VERSION = "1.0.0-baseline"


def _source_row_for_label(order: Any, piece_label: str) -> Any:
    try:
        group_no = int(str(piece_label).split(".", 1)[0])
    except (TypeError, ValueError):
        frappe.throw(_("Invalid original piece label {0}.").format(piece_label))

    if group_no < 1 or group_no > len(order.pieces or []):
        frappe.throw(_("Piece label {0} does not exist in order {1}.").format(piece_label, order.name))
    return order.pieces[group_no - 1]


def _edge_meters(replacement: Any) -> float:
    long_edges = cint(replacement.edge_long_right) + cint(replacement.edge_long_left)
    width_edges = cint(replacement.edge_width_top) + cint(replacement.edge_width_bottom)
    return (
        flt(replacement.length_cm) * long_edges
        + flt(replacement.width_cm) * width_edges
    ) / 100


def _edge_rate(edge_type: str | None) -> float:
    if not edge_type:
        return 0.0
    return flt(frappe.db.get_value("Edge Banding Type", edge_type, "rate_usd_per_meter"))


def _remnant_fits(remnant: Any, width_cm: float, length_cm: float, allow_rotation: bool, trim_mm: float) -> bool:
    usable_w = flt(remnant.width_mm) - (2 * flt(trim_mm))
    usable_h = flt(remnant.length_mm) - (2 * flt(trim_mm))
    width_mm = flt(width_cm) * 10
    length_mm = flt(length_cm) * 10
    normal = width_mm <= usable_w and length_mm <= usable_h
    rotated = allow_rotation and length_mm <= usable_w and width_mm <= usable_h
    return normal or rotated


def find_best_matching_remnant(
    board_item: str,
    width_cm: float,
    length_cm: float,
    allow_rotation: bool,
    trim_mm: float = 0,
) -> str | None:
    candidates = frappe.get_all(
        "Board Remnant",
        filters={"board_item": board_item, "status": "Available"},
        fields=["name", "width_mm", "length_mm", "area_m2"],
        order_by="area_m2 asc, modified asc",
    )
    for candidate in candidates:
        if _remnant_fits(candidate, width_cm, length_cm, allow_rotation, trim_mm):
            return candidate.name
    return None


def _lock_and_reserve_best_remnant(replacement: Any, order: Any) -> Any | None:
    settings = frappe.get_single("Almdina ERP Settings")
    if not cint(settings.prefer_remnants_before_full_boards) or replacement.source_preference == "Full Board":
        return None

    rows = frappe.db.sql(
        """
        select name, board_item, length_mm, width_mm, thickness_mm, material, color,
               area_m2, warehouse, location, parent_remnant
        from `tabBoard Remnant`
        where board_item = %s and status = 'Available'
        order by area_m2 asc, creation asc
        for update
        """,
        (replacement.board_item,),
        as_dict=True,
    )
    for remnant in rows:
        if not _remnant_fits(
            remnant,
            replacement.width_cm,
            replacement.length_cm,
            bool(replacement.allow_rotation),
            flt(order.trim_margin_mm),
        ):
            continue
        frappe.db.set_value(
            "Board Remnant",
            remnant.name,
            {
                "status": "Reserved",
                "reserved_for_order": order.name,
                "reservation_timestamp": now_datetime(),
            },
            update_modified=True,
        )
        return remnant
    return None


def _build_replacement_snapshot(order: Any, replacement: Any, remnant: Any | None) -> dict[str, Any]:
    trim_cm = flt(order.trim_margin_mm) / 10
    kerf_cm = flt(order.kerf_mm) / 10

    if remnant:
        source_type = "Remnant"
        full_w_cm = flt(remnant.width_mm) / 10
        full_h_cm = flt(remnant.length_mm) / 10
        remnant_name = remnant.name
    else:
        source_type = "Full Board"
        full_w_cm = flt(order.full_board_width_mm) / 10
        full_h_cm = flt(order.full_board_length_mm) / 10
        remnant_name = None

    usable_w = full_w_cm - (2 * trim_cm)
    usable_h = full_h_cm - (2 * trim_cm)
    if usable_w <= 0 or usable_h <= 0:
        frappe.throw(_("The selected source has no usable area after Trim Margin."))

    original_w = flt(replacement.width_cm)
    original_h = flt(replacement.length_cm)
    rotated = False
    placed_w = original_w
    placed_h = original_h

    if placed_w > usable_w or placed_h > usable_h:
        if cint(replacement.allow_rotation) and original_h <= usable_w and original_w <= usable_h:
            rotated = True
            placed_w = original_h
            placed_h = original_w
        else:
            frappe.throw(
                _("Replacement piece {0} does not fit the selected source with the current Trim Margin.").format(
                    replacement.original_piece_label
                )
            )

    piece_area = original_w * original_h / 10000
    source_area = usable_w * usable_h / 10000
    waste_area = max(0.0, source_area - piece_area)

    piece = {
        "id": 1,
        "label": f"{replacement.original_piece_label}-R",
        "source_piece_no": 1,
        "copy_no": 1,
        "group_qty": 1,
        "x": 0.0,
        "y": 0.0,
        "w": placed_w,
        "h": placed_h,
        "original_w": original_w,
        "original_h": original_h,
        "rotated": rotated,
        "area_m2": piece_area,
        "notes": replacement.notes or "",
        "edge_long_right": cint(replacement.edge_long_right),
        "edge_long_left": cint(replacement.edge_long_left),
        "edge_width_top": cint(replacement.edge_width_top),
        "edge_width_bottom": cint(replacement.edge_width_bottom),
        "edge_type": replacement.edge_type or "",
    }
    sheet = {
        "sheet_no": 1,
        "w": usable_w,
        "h": usable_h,
        "pieces": [piece],
        "source_type": source_type,
        "remnant": remnant_name,
        "board_item": replacement.board_item,
        "full_width_cm": full_w_cm,
        "full_length_cm": full_h_cm,
        "usable_width_cm": usable_w,
        "usable_length_cm": usable_h,
        "source_area_m2": source_area,
    }
    return {
        "engine_version": ENGINE_VERSION,
        "method_key": "Replacement Mini Plan",
        "method_label": f"Replacement Mini Plan - {source_type}",
        "score": waste_area * 1000,
        "full_board_width_cm": flt(order.full_board_width_mm) / 10,
        "full_board_length_cm": flt(order.full_board_length_mm) / 10,
        "usable_board_width_cm": flt(order.full_board_width_mm) / 10 - (2 * trim_cm),
        "usable_board_length_cm": flt(order.full_board_length_mm) / 10 - (2 * trim_cm),
        "kerf_cm": kerf_cm,
        "trim_cm": trim_cm,
        "used_area_m2": piece_area,
        "total_board_area_m2": source_area,
        "waste_area_m2": waste_area,
        "required_full_boards": 0 if remnant else 1,
        "used_remnants": [remnant_name] if remnant_name else [],
        "sheets": [sheet],
        "unplaced": [],
        "validation": {"is_valid": True, "errors": []},
    }


def _remnant_material_cost(order: Any, piece_area_m2: float) -> float:
    settings = frappe.get_single("Almdina ERP Settings")
    policy = settings.remnant_cost_policy or "Zero"
    if policy == "Configured Rate":
        return piece_area_m2 * flt(settings.remnant_rate_usd_per_m2)
    if policy == "Average Valuation":
        warehouse = settings.default_warehouse
        valuation_rate = flt(
            frappe.db.get_value(
                "Bin",
                {"item_code": order.board_item, "warehouse": warehouse},
                "valuation_rate",
            )
        )
        full_area = flt(order.full_board_width_mm) * flt(order.full_board_length_mm) / 1_000_000
        return valuation_rate * (piece_area_m2 / full_area) if full_area else 0.0
    return 0.0


def _create_mini_plan(order: Any, replacement: Any, snapshot: dict[str, Any], remnant: Any | None) -> Any:
    existing = frappe.db.get_value(
        "Cutting Plan",
        {"replacement_piece": replacement.name, "status": "Approved"},
        "name",
    )
    if existing:
        return frappe.get_doc("Cutting Plan", existing)

    edge_meters = _edge_meters(replacement)
    edge_cost = edge_meters * _edge_rate(replacement.edge_type)
    material_cost = (
        _remnant_material_cost(order, flt(snapshot["used_area_m2"]))
        if remnant
        else flt(order.board_rate_usd)
    )
    cutting_cost = flt(order.cutting_cost_per_board_usd or 1)
    planned_total = material_cost + cutting_cost + edge_cost

    plan = frappe.new_doc("Cutting Plan")
    plan.plan_kind = "Replacement"
    plan.door_cutting_order = order.name
    plan.replacement_piece = replacement.name
    plan.revision = 1
    plan.status = "Draft"
    plan.method_key = snapshot["method_key"]
    plan.method_label = snapshot["method_label"]
    plan.score = flt(snapshot["score"])
    plan.engine_version = snapshot["engine_version"]
    plan.validation_status = "Valid"
    plan.validation_errors = ""
    plan.board_item = replacement.board_item
    source = snapshot["sheets"][0]
    plan.full_board_width_mm = flt(source["full_width_cm"]) * 10
    plan.full_board_length_mm = flt(source["full_length_cm"]) * 10
    plan.usable_board_width_mm = flt(source["usable_width_cm"]) * 10
    plan.usable_board_length_mm = flt(source["usable_length_cm"]) * 10
    plan.kerf_mm = flt(order.kerf_mm)
    plan.trim_margin_mm = flt(order.trim_margin_mm)
    plan.required_boards = cint(snapshot["required_full_boards"])
    plan.used_area_m2 = flt(snapshot["used_area_m2"])
    plan.total_source_area_m2 = flt(snapshot["total_board_area_m2"])
    plan.waste_area_m2 = flt(snapshot["waste_area_m2"])
    plan.waste_percent = (
        flt(plan.waste_area_m2) / flt(plan.total_source_area_m2) * 100
        if flt(plan.total_source_area_m2)
        else 0
    )
    plan.board_rate_usd = flt(order.board_rate_usd)
    plan.cutting_cost_per_board_usd = flt(order.cutting_cost_per_board_usd or 1)
    plan.mdf_cost_usd = material_cost
    plan.cutting_cost_usd = cutting_cost
    plan.edge_cost_usd = edge_cost
    plan.total_cost_usd = planned_total
    plan.snapshot_json = frappe.as_json(snapshot)

    plan.append(
        "sources",
        {
            "sheet_no": 1,
            "source_type": source["source_type"],
            "board_item": replacement.board_item,
            "remnant": source.get("remnant"),
            "full_width_mm": flt(source["full_width_cm"]) * 10,
            "full_length_mm": flt(source["full_length_cm"]) * 10,
            "usable_width_mm": flt(source["usable_width_cm"]) * 10,
            "usable_length_mm": flt(source["usable_length_cm"]) * 10,
            "source_area_m2": flt(source["source_area_m2"]),
            "used_area_m2": flt(snapshot["used_area_m2"]),
            "waste_area_m2": flt(snapshot["waste_area_m2"]),
        },
    )
    piece = source["pieces"][0]
    plan.append(
        "placed_pieces",
        {
            "sheet_no": 1,
            "piece_id": 1,
            "piece_label": piece["label"],
            "source_piece_no": 1,
            "copy_no": 1,
            "x_mm": flt(piece["x"]) * 10,
            "y_mm": flt(piece["y"]) * 10,
            "width_mm": flt(piece["w"]) * 10,
            "height_mm": flt(piece["h"]) * 10,
            "original_width_cm": flt(piece["original_w"]),
            "original_length_cm": flt(piece["original_h"]),
            "rotated": cint(piece["rotated"]),
            "edge_long_right": cint(piece["edge_long_right"]),
            "edge_long_left": cint(piece["edge_long_left"]),
            "edge_width_top": cint(piece["edge_width_top"]),
            "edge_width_bottom": cint(piece["edge_width_bottom"]),
            "edge_type": piece.get("edge_type") or "",
            "notes": piece.get("notes") or "",
        },
    )
    plan.insert(ignore_permissions=True)
    plan.flags.allow_status_transition = True
    plan.status = "Approved"
    plan.approved_by = frappe.session.user
    plan.approved_on = now_datetime()
    plan.save(ignore_permissions=True)
    return plan


def _replacement_materials(replacement: Any, plan: Any) -> list[dict[str, Any]]:
    from almdina_erp.almdina_erp.services.stock_service import _meter_to_stock_qty

    materials: list[dict[str, Any]] = []
    if cint(plan.required_boards):
        materials.append(
            {
                "item_code": replacement.board_item,
                "qty": 1.0,
                "planned_unit": "Board",
                "planned_qty": 1.0,
            }
        )

    meters = _edge_meters(replacement)
    if replacement.edge_type and meters > 0:
        edge = frappe.db.get_value(
            "Edge Banding Type",
            replacement.edge_type,
            ["item_code", "disabled"],
            as_dict=True,
        )
        if not edge or cint(edge.disabled):
            frappe.throw(_("Edge Banding Type {0} is disabled or missing.").format(replacement.edge_type))
        if not edge.item_code:
            frappe.throw(
                _("Map Edge Banding Type {0} to a stock Item before approving this replacement.").format(
                    replacement.edge_type
                )
            )
        stock_qty, _ = _meter_to_stock_qty(edge.item_code, meters)
        materials.append(
            {
                "item_code": edge.item_code,
                "qty": stock_qty,
                "planned_unit": "Meter",
                "planned_qty": meters,
            }
        )
    return materials


def _reserved_qty_other(item_code: str, warehouse: str, replacement_name: str) -> float:
    result = frappe.db.sql(
        """
        select coalesce(sum(child.qty), 0)
        from `tabMaterial Reservation Item` child
        inner join `tabMaterial Reservation` parent on parent.name = child.parent
        where parent.status = 'Active'
          and child.item_code = %s
          and child.warehouse = %s
          and coalesce(parent.replacement_piece, '') != %s
        """,
        (item_code, warehouse, replacement_name),
    )
    return flt((result or [[0]])[0][0])


def _reserve_replacement_materials(replacement: Any, plan: Any) -> str | None:
    settings = frappe.get_single("Almdina ERP Settings")
    warehouse = settings.default_warehouse
    if not warehouse:
        frappe.throw(_("Set Default Warehouse before approving a replacement."))

    materials = _replacement_materials(replacement, plan)
    if not materials:
        return None

    for item_code in sorted({row["item_code"] for row in materials}):
        frappe.db.sql(
            "select name from `tabBin` where item_code = %s and warehouse = %s for update",
            (item_code, warehouse),
        )

    for material in materials:
        actual = flt(
            frappe.db.get_value(
                "Bin",
                {"item_code": material["item_code"], "warehouse": warehouse},
                "actual_qty",
            )
        )
        reserved_other = _reserved_qty_other(material["item_code"], warehouse, replacement.name)
        available = actual - reserved_other
        if available + 1e-9 < flt(material["qty"]):
            frappe.throw(
                _("Insufficient stock for replacement: {0}, required {1}, available {2} in {3}.").format(
                    material["item_code"], material["qty"], max(0, available), warehouse
                )
            )

    reservation = frappe.new_doc("Material Reservation")
    reservation.door_cutting_order = replacement.door_cutting_order
    reservation.cutting_plan = plan.name
    reservation.replacement_piece = replacement.name
    reservation.status = "Active"
    reservation.reserved_on = now_datetime()
    for material in materials:
        reservation.append(
            "items",
            {
                "item_code": material["item_code"],
                "warehouse": warehouse,
                "qty": material["qty"],
                "planned_unit": material["planned_unit"],
                "planned_qty": material["planned_qty"],
            },
        )
    reservation.insert(ignore_permissions=True)
    return reservation.name


def _make_replacement_stock_entry(replacement: Any, plan: Any) -> str | None:
    reservation_name = frappe.db.get_value(
        "Material Reservation",
        {"replacement_piece": replacement.name, "cutting_plan": plan.name, "status": "Active"},
        "name",
    )
    if not reservation_name:
        return None

    reservation = frappe.get_doc("Material Reservation", reservation_name)
    if not reservation.items:
        return None
    warehouse = reservation.items[0].warehouse
    company = frappe.db.get_value("Warehouse", warehouse, "company")
    if not company:
        frappe.throw(_("Warehouse {0} is not linked to a Company.").format(warehouse))

    entry = frappe.new_doc("Stock Entry")
    if entry.meta.has_field("stock_entry_type"):
        entry.stock_entry_type = "Material Issue"
    if entry.meta.has_field("purpose"):
        entry.purpose = "Material Issue"
    if entry.meta.has_field("company"):
        entry.company = company
    entry.remarks = _("Replacement material issue | {0} | Plan {1}").format(replacement.name, plan.name)
    for row in reservation.items:
        entry.append(
            "items",
            {
                "item_code": row.item_code,
                "s_warehouse": row.warehouse,
                "qty": flt(row.qty),
            },
        )
    entry.insert(ignore_permissions=True)
    entry.submit()

    reservation.flags.allow_status_transition = True
    reservation.status = "Consumed"
    reservation.released_on = now_datetime()
    reservation.save(ignore_permissions=True)
    return entry.name


def _consume_selected_remnant(replacement: Any) -> None:
    if not replacement.selected_remnant:
        return
    rows = frappe.db.sql(
        "select status, reserved_for_order from `tabBoard Remnant` where name = %s for update",
        (replacement.selected_remnant,),
        as_dict=True,
    )
    if not rows or rows[0].status != "Reserved" or rows[0].reserved_for_order != replacement.door_cutting_order:
        frappe.throw(_("The selected remnant reservation is no longer valid."))
    frappe.db.set_value(
        "Board Remnant",
        replacement.selected_remnant,
        {"status": "Consumed", "reserved_for_order": None, "reservation_timestamp": None},
        update_modified=True,
    )


def _qualifies_as_remnant(width_mm: float, length_mm: float) -> bool:
    settings = frappe.get_single("Almdina ERP Settings")
    area = flt(width_mm) * flt(length_mm) / 1_000_000
    return (
        flt(width_mm) >= flt(settings.min_remnant_width_mm)
        and flt(length_mm) >= flt(settings.min_remnant_length_mm)
        and area >= flt(settings.min_remnant_area_m2)
    )


def _create_generated_remnants(replacement: Any, plan: Any) -> list[str]:
    if frappe.db.exists("Board Remnant", {"source_plan": plan.name}):
        return frappe.get_all("Board Remnant", filters={"source_plan": plan.name}, pluck="name")

    source = plan.sources[0]
    piece = plan.placed_pieces[0]
    usable_w = flt(source.usable_width_mm)
    usable_h = flt(source.usable_length_mm)
    piece_w = flt(piece.width_mm)
    piece_h = flt(piece.height_mm)
    kerf = flt(plan.kerf_mm)

    candidates = [
        (max(0.0, usable_w - piece_w - kerf), usable_h),
        (piece_w, max(0.0, usable_h - piece_h - kerf)),
    ]

    settings = frappe.get_single("Almdina ERP Settings")
    warehouse = settings.default_warehouse
    location = ""
    parent_remnant = None
    if source.source_type == "Remnant" and source.remnant:
        parent = frappe.db.get_value(
            "Board Remnant",
            source.remnant,
            ["warehouse", "location"],
            as_dict=True,
        )
        if parent:
            warehouse = parent.warehouse or warehouse
            location = parent.location or ""
        parent_remnant = source.remnant

    created: list[str] = []
    for width_mm, length_mm in candidates:
        if not _qualifies_as_remnant(width_mm, length_mm):
            continue
        remnant = frappe.new_doc("Board Remnant")
        remnant.board_item = replacement.board_item
        remnant.warehouse = warehouse
        remnant.location = location
        remnant.width_mm = width_mm
        remnant.length_mm = length_mm
        remnant.source_order = replacement.door_cutting_order
        remnant.source_plan = plan.name
        remnant.parent_remnant = parent_remnant
        remnant.notes = _("Generated from replacement {0}").format(replacement.name)
        remnant.insert(ignore_permissions=True)
        created.append(remnant.name)
    return created


def _sync_replacement_order_status(order_name: str) -> str:
    open_count = frappe.db.count(
        "Replacement Piece",
        filters={"door_cutting_order": order_name, "status": ["not in", ["Completed", "Cancelled"]]},
    )
    if open_count:
        status = "Replacement Required"
        frappe.db.set_value("Door Cutting Order", order_name, "status", status, update_modified=True)
        return status

    from almdina_erp.almdina_erp.services.production_service import sync_order_status

    return sync_order_status(order_name)


@frappe.whitelist()
def record_incident(
    order_name: str,
    piece_label: str,
    reason: str,
    description: str,
    production_stage: str | None = None,
    requires_replacement: int | bool = 1,
) -> dict[str, Any]:
    require_any_role("Cutting Operator", "Edge Operator", "Production Manager")
    order = frappe.get_doc("Door Cutting Order", order_name)
    _source_row_for_label(order, piece_label)

    incident = frappe.new_doc("Production Incident")
    incident.door_cutting_order = order.name
    incident.piece_label = piece_label
    incident.production_stage = production_stage
    incident.worker = frappe.session.user
    incident.reason = reason
    incident.description = description
    incident.requires_replacement = cint(requires_replacement)
    incident.insert(ignore_permissions=True)

    replacement_name = None
    if incident.requires_replacement:
        replacement = _create_replacement(incident, order)
        replacement_name = replacement.name

    return {
        "incident": incident.name,
        "status": incident.status,
        "replacement_piece": replacement_name,
        "order_status": frappe.db.get_value("Door Cutting Order", order.name, "status"),
    }


def _create_replacement(incident: Any, order: Any) -> Any:
    if incident.replacement_piece:
        return frappe.get_doc("Replacement Piece", incident.replacement_piece)

    source_row = _source_row_for_label(order, incident.piece_label)
    replacement = frappe.new_doc("Replacement Piece")
    replacement.door_cutting_order = order.name
    replacement.incident = incident.name
    replacement.original_piece_label = incident.piece_label
    replacement.status = "Pending Approval"
    replacement.board_item = order.board_item
    replacement.width_cm = flt(source_row.width_cm)
    replacement.length_cm = flt(source_row.length_cm)
    replacement.qty = 1
    replacement.allow_rotation = cint(source_row.allow_rotation)
    replacement.edge_long_right = cint(source_row.edge_long_right)
    replacement.edge_long_left = cint(source_row.edge_long_left)
    replacement.edge_width_top = cint(source_row.edge_width_top)
    replacement.edge_width_bottom = cint(source_row.edge_width_bottom)
    replacement.edge_type = source_row.edge_type or order.default_edge_type or ""
    replacement.source_preference = "Remnant First"
    replacement.charge_customer = 0
    replacement.insert(ignore_permissions=True)

    frappe.db.set_value(
        "Production Incident",
        incident.name,
        {"status": "Replacement Created", "replacement_piece": replacement.name},
        update_modified=True,
    )
    frappe.db.set_value("Door Cutting Order", order.name, "status", "Replacement Required", update_modified=True)
    return replacement


@frappe.whitelist()
def create_replacement_from_incident(incident_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    incident = frappe.get_doc("Production Incident", incident_name)
    if not cint(incident.requires_replacement):
        frappe.throw(_("This incident is not marked as requiring a replacement."))
    order = frappe.get_doc("Door Cutting Order", incident.door_cutting_order)
    replacement = _create_replacement(incident, order)
    return {"replacement_piece": replacement.name, "status": replacement.status}


@frappe.whitelist()
def approve_replacement(replacement_name: str) -> dict[str, Any]:
    require_any_role("Production Manager")
    frappe.db.sql("select name from `tabReplacement Piece` where name = %s for update", (replacement_name,))
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "Pending Approval":
        frappe.throw(_("Only a Pending Approval replacement can be approved."))

    order = frappe.get_doc("Door Cutting Order", replacement.door_cutting_order)
    remnant = _lock_and_reserve_best_remnant(replacement, order)
    snapshot = _build_replacement_snapshot(order, replacement, remnant)
    plan = _create_mini_plan(order, replacement, snapshot, remnant)
    _reserve_replacement_materials(replacement, plan)

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Approved",
            "approved_by": frappe.session.user,
            "approved_on": now_datetime(),
            "selected_remnant": remnant.name if remnant else None,
            "cutting_plan": plan.name,
            "planned_internal_loss_usd": flt(plan.total_cost_usd),
            "charge_customer": 0,
        },
        update_modified=True,
    )
    return {
        "replacement_piece": replacement.name,
        "status": "Approved",
        "cutting_plan": plan.name,
        "selected_remnant": remnant.name if remnant else None,
        "planned_internal_loss_usd": flt(plan.total_cost_usd),
    }


@frappe.whitelist()
def start_replacement(replacement_name: str) -> dict[str, Any]:
    require_any_role("Cutting Operator", "Production Manager")
    frappe.db.sql("select name from `tabReplacement Piece` where name = %s for update", (replacement_name,))
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "Approved":
        frappe.throw(_("Only an Approved replacement can be started."))
    if not replacement.cutting_plan:
        frappe.throw(_("Replacement has no approved Mini Cutting Plan."))

    plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
    if plan.status != "Approved" or plan.plan_kind != "Replacement":
        frappe.throw(_("Replacement Mini Cutting Plan is not approved."))

    stock_entry = _make_replacement_stock_entry(replacement, plan)
    _consume_selected_remnant(replacement)
    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "In Progress",
            "started_by": frappe.session.user,
            "started_on": now_datetime(),
            "stock_entry": stock_entry,
        },
        update_modified=True,
    )
    return {
        "replacement_piece": replacement.name,
        "status": "In Progress",
        "stock_entry": stock_entry,
        "cutting_plan": plan.name,
    }


@frappe.whitelist()
def complete_replacement(
    replacement_name: str,
    internal_loss_cost_usd: float | None = None,
) -> dict[str, Any]:
    require_any_role("Cutting Operator", "Production Manager")
    frappe.db.sql("select name from `tabReplacement Piece` where name = %s for update", (replacement_name,))
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status != "In Progress":
        frappe.throw(_("Only an In Progress replacement can be completed."))

    plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
    generated = _create_generated_remnants(replacement, plan)
    actual_loss = (
        flt(internal_loss_cost_usd)
        if internal_loss_cost_usd is not None
        else flt(replacement.planned_internal_loss_usd)
    )
    largest = None
    if generated:
        largest = max(
            generated,
            key=lambda name: flt(frappe.db.get_value("Board Remnant", name, "area_m2")),
        )

    frappe.db.set_value(
        "Replacement Piece",
        replacement.name,
        {
            "status": "Completed",
            "internal_loss_cost_usd": actual_loss,
            "charge_customer": 0,
            "completed_by": frappe.session.user,
            "completed_on": now_datetime(),
            "generated_remnant": largest,
            "generated_remnants_json": frappe.as_json(generated),
        },
        update_modified=True,
    )
    frappe.db.set_value("Production Incident", replacement.incident, "status", "Resolved", update_modified=True)
    order_status = _sync_replacement_order_status(replacement.door_cutting_order)

    return {
        "replacement_piece": replacement.name,
        "status": "Completed",
        "order_status": order_status,
        "internal_loss_cost_usd": actual_loss,
        "charge_customer": 0,
        "generated_remnants": generated,
    }


@frappe.whitelist()
def cancel_replacement(replacement_name: str, reason: str | None = None) -> dict[str, Any]:
    require_any_role("Production Manager")
    frappe.db.sql("select name from `tabReplacement Piece` where name = %s for update", (replacement_name,))
    replacement = frappe.get_doc("Replacement Piece", replacement_name)
    if replacement.status == "Completed":
        frappe.throw(_("A completed replacement cannot be cancelled."))
    if replacement.status == "In Progress" or replacement.stock_entry:
        frappe.throw(_("A started replacement cannot be cancelled automatically because material has already been consumed."))

    if replacement.selected_remnant:
        frappe.db.sql("select name from `tabBoard Remnant` where name = %s for update", (replacement.selected_remnant,))
        current = frappe.db.get_value(
            "Board Remnant",
            replacement.selected_remnant,
            ["status", "reserved_for_order"],
            as_dict=True,
        )
        if current and current.status == "Reserved" and current.reserved_for_order == replacement.door_cutting_order:
            frappe.db.set_value(
                "Board Remnant",
                replacement.selected_remnant,
                {"status": "Available", "reserved_for_order": None, "reservation_timestamp": None},
                update_modified=True,
            )

    reservations = frappe.get_all(
        "Material Reservation",
        filters={"replacement_piece": replacement.name, "status": "Active"},
        pluck="name",
    )
    for name in reservations:
        reservation = frappe.get_doc("Material Reservation", name)
        reservation.flags.allow_status_transition = True
        reservation.status = "Released"
        reservation.released_on = now_datetime()
        reservation.save(ignore_permissions=True)

    if replacement.cutting_plan:
        plan = frappe.get_doc("Cutting Plan", replacement.cutting_plan)
        if plan.status == "Approved":
            plan.flags.allow_status_transition = True
            plan.status = "Cancelled"
            plan.save(ignore_permissions=True)

    frappe.db.set_value("Replacement Piece", replacement.name, "status", "Cancelled", update_modified=True)
    frappe.db.set_value("Production Incident", replacement.incident, "status", "Resolved", update_modified=True)
    if reason:
        replacement.add_comment("Comment", text=_("Replacement cancelled: {0}").format(reason))
    order_status = _sync_replacement_order_status(replacement.door_cutting_order)
    return {"replacement_piece": replacement.name, "status": "Cancelled", "order_status": order_status}
