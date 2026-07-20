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
    plan_name = frappe.db.get_value(
        "Door Cutting Order", order_name, "approved_plan"
    ) or frappe.db.get_value(
        "Cutting Plan",
        {"door_cutting_order": order_name, "status": "Approved"},
        "name",
        order_by="revision desc",
    )
    if not plan_name:
        frappe.throw(_("Order {0} has no approved Cutting Plan.").format(order_name))
    return frappe.get_doc("Cutting Plan", plan_name)


def _stock_balance(item_code: str, warehouse: str) -> float:
    return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


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


def _planned_materials(order: Any, plan: Any) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []

    full_board_count = sum(1 for source in (plan.sources or []) if source.source_type == "Full Board")
    if full_board_count:
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
            frappe.throw(
                _("Map Edge Banding Type {0} to a stock Item before approving/consuming this order.").format(edge_type)
            )

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


def validate_stock_for_order(order_name: str, *, throw_on_shortage: bool = True) -> dict[str, Any]:
    order = frappe.get_doc("Door Cutting Order", order_name)
    plan = _approved_plan(order_name)
    settings = get_settings()
    warehouse = settings.default_warehouse
    if not warehouse:
        frappe.throw(_("Set Default Warehouse in Almdina ERP Settings before approving/starting production."))

    materials = _planned_materials(order, plan)
    shortages: list[dict[str, Any]] = []
    balances: list[dict[str, Any]] = []

    for material in materials:
        actual_qty = _stock_balance(material["item_code"], warehouse)
        required_qty = flt(material["qty"])
        row = {
            **material,
            "warehouse": warehouse,
            "actual_qty": actual_qty,
            "required_qty": required_qty,
            "shortage_qty": max(0, required_qty - actual_qty),
        }
        balances.append(row)
        if actual_qty + 1e-9 < required_qty:
            shortages.append(row)

    if shortages and throw_on_shortage:
        lines = [
            _("{0}: required {1}, available {2} in {3}").format(
                row["item_code"], row["required_qty"], row["actual_qty"], warehouse
            )
            for row in shortages
        ]
        frappe.throw(_("Insufficient stock:\n{0}").format("\n".join(lines)))

    return {"warehouse": warehouse, "materials": balances, "shortages": shortages, "is_available": not shortages}


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
    stock_entry.remarks = _(
        "Almdina ERP planned material consumption for Door Cutting Order {0}, Cutting Plan {1}"
    ).format(order.name, plan.name)

    for material in materials:
        qty = flt(material["qty"])
        if qty <= 0:
            continue
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

    availability = validate_stock_for_order(order.name, throw_on_shortage=True)
    stock_entry = _make_material_issue(order, plan, availability["warehouse"], availability["materials"])
    consumed_remnants = _consume_reserved_remnants(order, plan)

    log = frappe.new_doc("Material Consumption Log")
    log.door_cutting_order = order.name
    log.cutting_plan = plan.name
    log.warehouse = availability["warehouse"]
    log.trigger_point = trigger
    log.status = "Submitted"
    log.stock_entry = stock_entry.name if stock_entry else None
    log.consumed_on = now_datetime()
    log.details_json = frappe.as_json({"stock_materials": availability["materials"], "consumed_remnants": consumed_remnants})
    log.insert(ignore_permissions=True)

    return {
        "log": log.name,
        "stock_entry": stock_entry.name if stock_entry else None,
        "consumed_remnants": consumed_remnants,
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
