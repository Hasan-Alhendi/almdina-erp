from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


METER_UOMS = {"meter", "metre", "meters", "metres", "m"}


def get_settings() -> Any:
    return frappe.get_single("Almdina ERP Settings")


def _approved_plan(order_name: str) -> Any:
    plan_name = frappe.db.get_value("Door Cutting Order", order_name, "approved_plan") or frappe.db.get_value(
        "Cutting Plan",
        {"door_cutting_order": order_name, "status": "Approved", "plan_kind": "Order"},
        "name",
        order_by="revision desc",
    )
    if not plan_name:
        frappe.throw(_("Order {0} has no approved Cutting Plan.").format(order_name))
    return frappe.get_doc("Cutting Plan", plan_name)


def _stock_balance(item_code: str, warehouse: str) -> float:
    return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def _active_reserved_qty(
    item_code: str,
    warehouse: str,
    *,
    exclude_reservation: str | None = None,
) -> float:
    """Return active reserved stock, excluding at most one exact reservation.

    Never exclude by Door Cutting Order: replacement reservations belonging to
    the same order are physically competing reservations and must still reduce
    availability for the main order (and vice versa).
    """
    conditions = ["parent.status = 'Active'", "child.item_code = %s", "child.warehouse = %s"]
    values: list[Any] = [item_code, warehouse]
    if exclude_reservation:
        conditions.append("parent.name != %s")
        values.append(exclude_reservation)

    result = frappe.db.sql(
        f"""
        select coalesce(sum(child.qty), 0)
        from `tabMaterial Reservation Item` child
        inner join `tabMaterial Reservation` parent on parent.name = child.parent
        where {' and '.join(conditions)}
        """,
        tuple(values),
    )
    return flt((result or [[0]])[0][0])


def _main_order_reservation_name(order_name: str, plan_name: str) -> str | None:
    rows = frappe.db.sql(
        """
        select name
        from `tabMaterial Reservation`
        where door_cutting_order = %s
          and cutting_plan = %s
          and status = 'Active'
          and coalesce(replacement_piece, '') = ''
        order by creation desc
        limit 1
        """,
        (order_name, plan_name),
    )
    return rows[0][0] if rows else None


def _meter_to_stock_qty(item_code: str, meters: float) -> tuple[float, str]:
    item = frappe.db.get_value("Item", item_code, ["stock_uom"], as_dict=True)
    if not item:
        frappe.throw(_("Stock Item {0} does not exist.").format(item_code))

    stock_uom = item.stock_uom or ""
    if stock_uom.strip().lower() in METER_UOMS:
        return flt(meters), stock_uom

    rows = frappe.get_all(
        "UOM Conversion Detail",
        filters={"parent": item_code, "parenttype": "Item"},
        fields=["uom", "conversion_factor"],
    )
    meter_row = next((row for row in rows if (row.uom or "").strip().lower() in METER_UOMS), None)
    if not meter_row or flt(meter_row.conversion_factor) <= 0:
        frappe.throw(
            _("Edge stock Item {0} uses Stock UOM {1}. Add a Meter UOM conversion before consumption.").format(
                item_code, stock_uom
            )
        )
    return flt(meters) * flt(meter_row.conversion_factor), stock_uom


def _validate_board_stock_uom(item_code: str) -> None:
    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
    if not stock_uom:
        frappe.throw(_("Board Item {0} has no Stock UOM.").format(item_code))
    whole = frappe.db.get_value("UOM", stock_uom, "must_be_whole_number")
    if not cint(whole):
        frappe.throw(
            _("Board Item {0} must use a whole-number Stock UOM because planned consumption is counted in physical boards.").format(
                item_code
            )
        )


def _planned_materials(order: Any, plan: Any) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []

    full_board_count = sum(1 for source in (plan.sources or []) if source.source_type == "Full Board")
    if full_board_count:
        _validate_board_stock_uom(order.board_item)
        materials.append(
            {
                "item_code": order.board_item,
                "qty": flt(full_board_count),
                "kind": "Board",
                "planned_unit": "Board",
                "planned_qty": flt(full_board_count),
            }
        )

    edge_meters: dict[str, float] = defaultdict(float)
    for row in order.pieces or []:
        edge_type = row.edge_type or order.default_edge_type
        if edge_type and flt(row.edge_meters) > 0:
            edge_meters[edge_type] += flt(row.edge_meters)

    for edge_type, meters in edge_meters.items():
        edge_master = frappe.db.get_value(
            "Edge Banding Type", edge_type, ["item_code", "stock_uom", "disabled"], as_dict=True
        )
        if not edge_master or cint(edge_master.disabled):
            frappe.throw(_("Edge Banding Type {0} is disabled or missing.").format(edge_type))
        if not edge_master.item_code:
            frappe.throw(_("Map Edge Banding Type {0} to a stock Item before approving/consuming this order.").format(edge_type))

        stock_qty, stock_uom = _meter_to_stock_qty(edge_master.item_code, meters)
        materials.append(
            {
                "item_code": edge_master.item_code,
                "qty": stock_qty,
                "kind": "Edge Banding",
                "edge_type": edge_type,
                "planned_unit": "Meter",
                "planned_qty": meters,
                "stock_uom": stock_uom,
            }
        )
    return materials


def validate_stock_for_order(
    order_name: str,
    *,
    throw_on_shortage: bool = True,
    exclude_own_reservation: bool = True,
) -> dict[str, Any]:
    order = frappe.get_doc("Door Cutting Order", order_name)
    plan = _approved_plan(order_name)
    settings = get_settings()
    warehouse = settings.default_warehouse
    if not warehouse:
        frappe.throw(_("Set Default Warehouse in Almdina ERP Settings before approving/starting production."))

    own_reservation = (
        _main_order_reservation_name(order.name, plan.name)
        if exclude_own_reservation
        else None
    )
    materials = _planned_materials(order, plan)
    shortages: list[dict[str, Any]] = []
    balances: list[dict[str, Any]] = []

    for material in materials:
        actual_qty = _stock_balance(material["item_code"], warehouse)
        reserved_other = _active_reserved_qty(
            material["item_code"],
            warehouse,
            exclude_reservation=own_reservation,
        )
        available_qty = max(0.0, actual_qty - reserved_other)
        required_qty = flt(material["qty"])
        row = {
            **material,
            "warehouse": warehouse,
            "actual_qty": actual_qty,
            "reserved_by_other_reservations": reserved_other,
            "available_qty": available_qty,
            "required_qty": required_qty,
            "shortage_qty": max(0, required_qty - available_qty),
        }
        balances.append(row)
        if available_qty + 1e-9 < required_qty:
            shortages.append(row)

    if shortages and throw_on_shortage:
        lines = [
            _("{0}: required {1}, available after reservations {2}, physical stock {3} in {4}").format(
                row["item_code"], row["required_qty"], row["available_qty"], row["actual_qty"], warehouse
            )
            for row in shortages
        ]
        frappe.throw(_("Insufficient stock:\n{0}").format("\n".join(lines)))

    return {
        "warehouse": warehouse,
        "materials": balances,
        "shortages": shortages,
        "is_available": not shortages,
        "excluded_reservation": own_reservation,
    }


def create_order_reservation(order_name: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not cint(settings.reserve_stock_on_approval):
        return None

    order = frappe.get_doc("Door Cutting Order", order_name)
    plan = _approved_plan(order_name)
    existing = _main_order_reservation_name(order.name, plan.name)
    if existing:
        return {"reservation": existing, "already_reserved": True}

    warehouse = settings.default_warehouse
    if not warehouse:
        frappe.throw(_("Set Default Warehouse in Almdina ERP Settings before approving production."))
    materials = _planned_materials(order, plan)

    # Lock Bin rows in deterministic order. Replacement reservations for the
    # same order are intentionally included in the competing reservations.
    for item_code in sorted({m["item_code"] for m in materials}):
        frappe.db.sql(
            "select name from `tabBin` where item_code = %s and warehouse = %s for update",
            (item_code, warehouse),
        )

    availability = validate_stock_for_order(order.name, throw_on_shortage=True, exclude_own_reservation=False)
    reservation = frappe.new_doc("Material Reservation")
    reservation.door_cutting_order = order.name
    reservation.cutting_plan = plan.name
    reservation.replacement_piece = None
    reservation.status = "Active"
    reservation.reserved_on = now_datetime()
    for material in availability["materials"]:
        reservation.append(
            "items",
            {
                "item_code": material["item_code"],
                "warehouse": warehouse,
                "qty": material["required_qty"],
                "planned_unit": material.get("planned_unit"),
                "planned_qty": material.get("planned_qty"),
            },
        )
    reservation.insert(ignore_permissions=True)
    return {"reservation": reservation.name, "already_reserved": False}


def transition_order_reservation(order_name: str, new_status: str, plan_name: str | None = None) -> list[str]:
    conditions = [
        "door_cutting_order = %s",
        "status = 'Active'",
        "coalesce(replacement_piece, '') = ''",
    ]
    values: list[Any] = [order_name]
    if plan_name:
        conditions.append("cutting_plan = %s")
        values.append(plan_name)

    names = [
        row[0]
        for row in frappe.db.sql(
            f"select name from `tabMaterial Reservation` where {' and '.join(conditions)} for update",
            tuple(values),
        )
    ]
    transitioned: list[str] = []
    for name in names:
        reservation = frappe.get_doc("Material Reservation", name)
        reservation.flags.allow_status_transition = True
        reservation.status = new_status
        reservation.released_on = now_datetime()
        reservation.save(ignore_permissions=True)
        transitioned.append(name)
    return transitioned


def _make_material_issue(order: Any, plan: Any, warehouse: str, materials: list[dict[str, Any]]) -> Any | None:
    if not any(flt(material.get("qty")) > 0 for material in materials):
        return None

    company = frappe.db.get_value("Warehouse", warehouse, "company")
    if not company:
        frappe.throw(_("Warehouse {0} is not linked to a Company.").format(warehouse))

    stock_entry = frappe.new_doc("Stock Entry")
    if stock_entry.meta.has_field("stock_entry_type"):
        stock_entry.stock_entry_type = "Material Issue"
    if stock_entry.meta.has_field("purpose"):
        stock_entry.purpose = "Material Issue"
    if stock_entry.meta.has_field("company"):
        stock_entry.company = company
    stock_entry.remarks = _("Almdina ERP material consumption | Door Cutting Order {0} | Cutting Plan {1}").format(order.name, plan.name)

    for material in materials:
        qty = flt(material["qty"])
        if qty > 0:
            stock_entry.append("items", {"item_code": material["item_code"], "s_warehouse": warehouse, "qty": qty})

    stock_entry.insert(ignore_permissions=True)
    stock_entry.submit()
    return stock_entry


def _consume_reserved_remnants(order: Any, plan: Any) -> list[str]:
    consumed: list[str] = []
    for source in plan.sources or []:
        if source.source_type != "Remnant" or not source.remnant:
            continue
        rows = frappe.db.sql(
            "select status, reserved_for_order from `tabBoard Remnant` where name = %s for update",
            (source.remnant,),
            as_dict=True,
        )
        if not rows:
            frappe.throw(_("Remnant {0} no longer exists.").format(source.remnant))
        state = rows[0]
        if state.status == "Consumed":
            consumed.append(source.remnant)
            continue
        if state.status != "Reserved" or state.reserved_for_order != order.name:
            frappe.throw(_("Remnant {0} is not reserved for this order.").format(source.remnant))
        frappe.db.set_value(
            "Board Remnant",
            source.remnant,
            {"status": "Consumed", "reserved_for_order": None, "reservation_timestamp": None},
            update_modified=True,
        )
        consumed.append(source.remnant)
    return consumed


def consume_planned_material_if_due(order_name: str, *, trigger: str) -> dict[str, Any] | None:
    settings = get_settings()
    if (settings.stock_consumption_point or "Cutting Start") != trigger:
        return None

    frappe.db.sql("select name from `tabDoor Cutting Order` where name = %s for update", (order_name,))
    order = frappe.get_doc("Door Cutting Order", order_name)
    plan = _approved_plan(order_name)

    existing = frappe.db.get_value(
        "Material Consumption Log",
        {"door_cutting_order": order.name, "cutting_plan": plan.name, "status": "Submitted"},
        ["name", "stock_entry"],
        as_dict=True,
    )
    if existing:
        return {"log": existing.name, "stock_entry": existing.stock_entry, "already_consumed": True}

    availability = validate_stock_for_order(order.name, throw_on_shortage=True, exclude_own_reservation=True)
    stock_entry = _make_material_issue(order, plan, availability["warehouse"], availability["materials"])
    consumed_remnants = _consume_reserved_remnants(order, plan)
    consumed_reservations = transition_order_reservation(order.name, "Consumed", plan.name)

    log = frappe.new_doc("Material Consumption Log")
    log.door_cutting_order = order.name
    log.cutting_plan = plan.name
    log.warehouse = availability["warehouse"]
    log.trigger_point = trigger
    log.status = "Submitted"
    log.stock_entry = stock_entry.name if stock_entry else None
    log.consumed_on = now_datetime()
    log.details_json = frappe.as_json(
        {
            "stock_materials": availability["materials"],
            "consumed_remnants": consumed_remnants,
            "consumed_reservations": consumed_reservations,
        }
    )
    log.insert(ignore_permissions=True)

    return {
        "log": log.name,
        "stock_entry": stock_entry.name if stock_entry else None,
        "consumed_remnants": consumed_remnants,
        "consumed_reservations": consumed_reservations,
        "already_consumed": False,
    }


@frappe.whitelist()
def check_order_stock(order_name: str) -> dict[str, Any]:
    require_any_role("Order Entry", "Cutting Operator", "Production Manager", "Stock Manager")
    return validate_stock_for_order(order_name, throw_on_shortage=False)


@frappe.whitelist()
def consume_order_materials(order_name: str) -> dict[str, Any] | None:
    require_any_role("Production Manager", "Stock Manager")
    settings = get_settings()
    return consume_planned_material_if_due(order_name, trigger=settings.stock_consumption_point or "Cutting Start")
