from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role
from almdina_erp.almdina_erp.services.stock_service import _active_reserved_qty, _stock_balance


def _planned_rows(log: Any) -> list[dict[str, Any]]:
    payload = frappe.parse_json(log.details_json or "{}") or {}
    return list(payload.get("stock_materials") or [])


def _normalize_actual(actual_materials: str | list[dict[str, Any]]) -> dict[str, float]:
    rows = frappe.parse_json(actual_materials) if isinstance(actual_materials, str) else actual_materials
    if not isinstance(rows, list):
        frappe.throw(_("Actual materials must be a list of item_code / actual_qty rows."))

    result: dict[str, float] = {}
    for row in rows:
        item_code = (row or {}).get("item_code")
        if not item_code:
            frappe.throw(_("Every actual-consumption row requires an Item."))
        if item_code in result:
            frappe.throw(_("Item {0} appears more than once in actual consumption.").format(item_code))
        actual_qty = flt((row or {}).get("actual_qty"))
        if actual_qty < 0:
            frappe.throw(_("Actual quantity for Item {0} cannot be negative.").format(item_code))
        result[item_code] = actual_qty
    return result


def _variance_cost_usd(material: dict[str, Any], delta_stock_qty: float, plan: Any) -> float:
    if abs(delta_stock_qty) < 1e-9:
        return 0.0

    kind = material.get("kind")
    planned_stock_qty = flt(material.get("required_qty") or material.get("qty"))
    planned_business_qty = flt(material.get("planned_qty"))

    if kind == "Board":
        return delta_stock_qty * flt(plan.board_rate_usd)

    if kind == "Edge Banding" and material.get("edge_type"):
        rate = flt(
            frappe.db.get_value(
                "Edge Banding Type",
                material.get("edge_type"),
                "rate_usd_per_meter",
            )
        )
        if planned_stock_qty > 0:
            cost_per_stock_unit = (planned_business_qty * rate) / planned_stock_qty
            return delta_stock_qty * cost_per_stock_unit

    return 0.0


def _create_adjustment_entry(
    *,
    warehouse: str,
    company: str,
    purpose: str,
    rows: list[dict[str, Any]],
    remarks: str,
) -> str | None:
    if not rows:
        return None

    entry = frappe.new_doc("Stock Entry")
    if entry.meta.has_field("stock_entry_type"):
        entry.stock_entry_type = purpose
    if entry.meta.has_field("purpose"):
        entry.purpose = purpose
    if entry.meta.has_field("company"):
        entry.company = company
    entry.remarks = remarks

    for row in rows:
        values = {
            "item_code": row["item_code"],
            "qty": flt(row["qty"]),
        }
        if purpose == "Material Issue":
            values["s_warehouse"] = warehouse
        else:
            values["t_warehouse"] = warehouse
        entry.append("items", values)

    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry.name


@frappe.whitelist()
def record_actual_consumption(
    consumption_log: str,
    actual_materials: str | list[dict[str, Any]],
) -> dict[str, Any]:
    require_any_role("Production Manager", "Stock Manager")

    frappe.db.sql(
        "select name from `tabMaterial Consumption Log` where name = %s for update",
        (consumption_log,),
    )
    log = frappe.get_doc("Material Consumption Log", consumption_log)
    if log.status != "Submitted":
        frappe.throw(_("Actual consumption can only be recorded for a Submitted consumption log."))
    if log.actual_recorded:
        frappe.throw(_("Actual consumption was already recorded for this log. Reverse the adjustment before recording again."))

    planned = _planned_rows(log)
    if not planned:
        frappe.throw(_("Consumption log has no planned stock materials to reconcile."))

    actual_by_item = _normalize_actual(actual_materials)
    planned_codes = {row.get("item_code") for row in planned if row.get("item_code")}
    actual_codes = set(actual_by_item)
    missing = planned_codes - actual_codes
    unknown = actual_codes - planned_codes
    if missing:
        frappe.throw(_("Actual consumption is missing planned Items: {0}").format(", ".join(sorted(missing))))
    if unknown:
        frappe.throw(_("Actual consumption contains Items not present in the approved plan: {0}").format(", ".join(sorted(unknown))))

    plan = frappe.get_doc("Cutting Plan", log.cutting_plan)
    warehouse = log.warehouse
    company = frappe.db.get_value("Warehouse", warehouse, "company")
    if not company:
        frappe.throw(_("Warehouse {0} is not linked to a Company.").format(warehouse))

    # Serialize competing stock adjustments and preserve all active reservations.
    for item_code in sorted(planned_codes):
        frappe.db.sql(
            "select name from `tabBin` where item_code = %s and warehouse = %s for update",
            (item_code, warehouse),
        )

    issue_rows: list[dict[str, Any]] = []
    return_rows: list[dict[str, Any]] = []
    variance_rows: list[dict[str, Any]] = []
    variance_cost = 0.0

    for material in planned:
        item_code = material["item_code"]
        planned_qty = flt(material.get("required_qty") or material.get("qty"))
        actual_qty = flt(actual_by_item[item_code])
        delta = actual_qty - planned_qty
        row_cost = _variance_cost_usd(material, delta, plan)
        variance_cost += row_cost

        stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or material.get("stock_uom")
        variance_rows.append(
            {
                "item_code": item_code,
                "stock_uom": stock_uom,
                "planned_qty": planned_qty,
                "actual_qty": actual_qty,
                "variance_qty": delta,
                "planned_unit": material.get("planned_unit") or "",
                "planned_business_qty": flt(material.get("planned_qty")),
                "variance_cost_usd": row_cost,
            }
        )

        if delta > 1e-9:
            physical = _stock_balance(item_code, warehouse)
            reserved = _active_reserved_qty(item_code, warehouse)
            freely_available = max(0.0, physical - reserved)
            if freely_available + 1e-9 < delta:
                frappe.throw(
                    _("Cannot issue extra {0} of Item {1}: only {2} is free after active reservations in {3}.").format(
                        delta, item_code, freely_available, warehouse
                    )
                )
            issue_rows.append({"item_code": item_code, "qty": delta})
        elif delta < -1e-9:
            return_rows.append({"item_code": item_code, "qty": abs(delta)})

    issue_entry = _create_adjustment_entry(
        warehouse=warehouse,
        company=company,
        purpose="Material Issue",
        rows=issue_rows,
        remarks=_("Additional actual consumption for {0} / order {1}").format(log.name, log.door_cutting_order),
    )
    return_entry = _create_adjustment_entry(
        warehouse=warehouse,
        company=company,
        purpose="Material Receipt",
        rows=return_rows,
        remarks=_("Unused material return for {0} / order {1}").format(log.name, log.door_cutting_order),
    )

    log.set("variance_items", [])
    for row in variance_rows:
        log.append("variance_items", row)
    log.actual_recorded = 1
    log.actual_recorded_by = frappe.session.user
    log.actual_recorded_on = now_datetime()
    log.adjustment_issue_stock_entry = issue_entry
    log.adjustment_return_stock_entry = return_entry
    log.material_variance_cost_usd = variance_cost
    log.actual_details_json = frappe.as_json(
        {
            "actual_materials": variance_rows,
            "additional_issue_stock_entry": issue_entry,
            "return_receipt_stock_entry": return_entry,
            "material_variance_cost_usd": variance_cost,
        }
    )
    log.save(ignore_permissions=True)

    from almdina_erp.almdina_erp.services.cost_service import sync_order_costs

    cost_summary = sync_order_costs(log.door_cutting_order)
    return {
        "consumption_log": log.name,
        "actual_recorded": True,
        "additional_issue_stock_entry": issue_entry,
        "return_receipt_stock_entry": return_entry,
        "material_variance_cost_usd": variance_cost,
        "variance_items": variance_rows,
        "cost_summary": cost_summary,
    }
