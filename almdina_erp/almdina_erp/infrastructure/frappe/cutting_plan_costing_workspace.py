from __future__ import annotations

from typing import Any, Mapping

import frappe
from frappe.utils import flt

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.domain.orders.costing import calculate_order_costs


PLAN_COST_FIELDS = (
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "mdf_cost_usd",
    "cutting_cost_usd",
    "edge_cost_usd",
    "total_cost_usd",
)


def _source_type(order: Any) -> str:
    source = str(getattr(order, "cutting_plan_source", None) or "System").strip().lower()
    return UPLOADED_DXF if source in {"custom", "uploaded dxf", "uploaded_dxf", "dxf"} else SYSTEM


def initial_plan_cost_values(
    order_name: str,
    *,
    based_on_plan: str | None = None,
) -> dict[str, float]:
    """Seed the financial snapshot only when a new plan revision is created.

    Plan lineage is authoritative once it exists. The DCO fallback is a one-time
    migration bridge for the first plan created for an older order; zero is a
    valid explicit price and is therefore copied exactly rather than treated as
    an uninitialized value.
    """

    source_doctype = "Cutting Plan" if based_on_plan else "Door Cutting Order"
    source_name = based_on_plan or order_name
    values = frappe.db.get_value(
        source_doctype,
        source_name,
        list(PLAN_COST_FIELDS),
        as_dict=True,
    ) or {}
    return {
        fieldname: flt(values.get(fieldname))
        for fieldname in PLAN_COST_FIELDS
    }


def apply_plan_costs(plan: Any, *, edge_cost_usd: float | None = None) -> dict[str, float]:
    """Calculate and store the plan-owned financial result without touching geometry."""

    edge_cost = flt(plan.edge_cost_usd) if edge_cost_usd is None else flt(edge_cost_usd)
    result = calculate_order_costs(
        required_boards=int(plan.required_boards or 0),
        board_rate_usd=flt(plan.board_rate_usd),
        cutting_cost_per_board_usd=flt(plan.cutting_cost_per_board_usd),
        edge_cost_usd=edge_cost,
    )
    values = {
        "board_rate_usd": flt(plan.board_rate_usd),
        "cutting_cost_per_board_usd": flt(plan.cutting_cost_per_board_usd),
        "mdf_cost_usd": result.mdf_cost_usd,
        "cutting_cost_usd": result.cutting_cost_usd,
        "edge_cost_usd": result.edge_cost_usd,
        "total_cost_usd": result.total_cost_usd,
    }
    for fieldname, value in values.items():
        setattr(plan, fieldname, value)
    return values


def project_plan_costs_to_order(order: Any, plan: Any) -> dict[str, float]:
    """Maintain legacy DCO financial fields as a one-way compatibility projection."""

    values = {fieldname: flt(getattr(plan, fieldname, 0)) for fieldname in PLAN_COST_FIELDS}
    meta = frappe.get_meta("Door Cutting Order")
    values = {key: value for key, value in values.items() if meta.has_field(key)}
    if values:
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            values,
            update_modified=False,
        )
        for fieldname, value in values.items():
            setattr(order, fieldname, value)
    return values


def current_cost_plan(order: Any) -> Any | None:
    """Resolve the plan used for financial reads without creating or mutating data."""

    source_type = _source_type(order)
    drafts = frappe.get_all(
        "Cutting Plan",
        filters={
            "door_cutting_order": order.name,
            "plan_kind": "Order",
            "source_type": source_type,
            "status": DRAFT,
        },
        pluck="name",
        order_by="revision desc, creation desc",
        limit_page_length=1,
    )
    if drafts:
        return frappe.get_doc("Cutting Plan", drafts[0])

    approved_plan = str(getattr(order, "approved_plan", None) or "").strip()
    if approved_plan and frappe.db.exists("Cutting Plan", approved_plan):
        return frappe.get_doc("Cutting Plan", approved_plan)

    latest = frappe.get_all(
        "Cutting Plan",
        filters={"door_cutting_order": order.name, "plan_kind": "Order"},
        pluck="name",
        order_by="revision desc, creation desc",
        limit_page_length=1,
    )
    return frappe.get_doc("Cutting Plan", latest[0]) if latest else None


def authoritative_cost_values(order: Any, *, plan: Any | None = None) -> dict[str, float]:
    """Return Plan-owned cost values, falling back only for pre-A3 legacy orders."""

    resolved_plan = plan if plan is not None else current_cost_plan(order)
    source = resolved_plan if resolved_plan is not None else order
    return {fieldname: flt(getattr(source, fieldname, 0)) for fieldname in PLAN_COST_FIELDS}


def overlay_authoritative_costs(
    order: Any,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Overlay the current plan cost projection onto a DCO-shaped read model."""

    result = dict(snapshot)
    plan = current_cost_plan(order)
    result.update(authoritative_cost_values(order, plan=plan))
    if plan is not None:
        result["required_boards"] = int(plan.required_boards or 0)
    return result


__all__ = [
    "PLAN_COST_FIELDS",
    "apply_plan_costs",
    "authoritative_cost_values",
    "current_cost_plan",
    "initial_plan_cost_values",
    "overlay_authoritative_costs",
    "project_plan_costs_to_order",
]
