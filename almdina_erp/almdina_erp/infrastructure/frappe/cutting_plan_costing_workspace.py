from __future__ import annotations

from typing import Any, Mapping

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT
from almdina_erp.almdina_erp.domain.orders.costing import (
    CostingError,
    SpecialPricingPieceInput,
    SpecialPricingSettings,
    calculate_order_costs,
    calculate_special_pricing,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    current_working_plan,
)


COST_SNAPSHOT_VERSION = 1
PLAN_COST_FIELDS = (
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "mdf_cost_usd",
    "cutting_cost_usd",
    "edge_cost_usd",
    "total_cost_usd",
)


def initial_plan_cost_values(
    order_name: str,
    *,
    based_on_plan: str | None = None,
) -> dict[str, float | int]:
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
        **{
            fieldname: flt(values.get(fieldname))
            for fieldname in PLAN_COST_FIELDS
        },
        "cost_snapshot_version": COST_SNAPSHOT_VERSION,
    }


def initialize_draft_plan_cost_snapshot(order: Any, plan: Any) -> bool:
    """Adopt one legacy Draft into A3 ownership without guessing from zero values."""

    if cint(getattr(plan, "cost_snapshot_version", 0)) >= COST_SNAPSHOT_VERSION:
        return False
    if str(getattr(plan, "status", None) or "") != DRAFT:
        return False

    values = initial_plan_cost_values(
        order.name,
        based_on_plan=str(getattr(plan, "based_on_plan", None) or "").strip() or None,
    )
    for fieldname, value in values.items():
        setattr(plan, fieldname, value)
    return True


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
    plan.cost_snapshot_version = COST_SNAPSHOT_VERSION
    return values


def persist_plan_cost_snapshot(plan: Any) -> dict[str, float | int]:
    """Persist one trusted server-calculated financial snapshot.

    Cutting Plan financial fields intentionally stay on permission level 1 so
    ordinary plan editors cannot read or edit them through Desk. Geometry and
    DXF commands, however, legitimately change derived cost totals whenever the
    required board count changes. Frappe can discard those protected field
    mutations during ``Document.save()`` for a user without that permlevel.

    This narrow infrastructure boundary therefore persists only the already
    calculated in-memory snapshot after the parent command has authorized the
    order and saved the Draft plan. It does not accept raw request values and it
    never grants the caller permission to edit cost inputs.
    """

    if str(getattr(plan, "status", None) or "") != DRAFT:
        frappe.throw(
            _("لا يمكن تحديث لقطة تكلفة خطة القص إلا على خطة في حالة المسودة."),
            frappe.ValidationError,
        )
    if not str(getattr(plan, "name", None) or "").strip():
        frappe.throw(_("تعذر حفظ تكلفة خطة القص قبل حفظ الخطة نفسها."), frappe.ValidationError)
    if cint(getattr(plan, "cost_snapshot_version", 0)) < COST_SNAPSHOT_VERSION:
        frappe.throw(
            _("لم يتم حساب لقطة تكلفة حديثة لخطة القص."),
            frappe.ValidationError,
        )

    values: dict[str, float | int] = {
        "cost_snapshot_version": COST_SNAPSHOT_VERSION,
        **{
            fieldname: flt(getattr(plan, fieldname, 0))
            for fieldname in PLAN_COST_FIELDS
        },
    }
    frappe.db.set_value(
        "Cutting Plan",
        plan.name,
        values,
        update_modified=False,
    )

    persisted = frappe.db.get_value(
        "Cutting Plan",
        plan.name,
        ["cost_snapshot_version", *PLAN_COST_FIELDS],
        as_dict=True,
    ) or {}
    if cint(persisted.get("cost_snapshot_version")) != COST_SNAPSHOT_VERSION or any(
        flt(persisted.get(fieldname)) != flt(values[fieldname])
        for fieldname in PLAN_COST_FIELDS
    ):
        frappe.throw(
            _(
                "تعذر حفظ تكلفة خطة القص المشتقة. "
                "أوقف النظام العملية لأن القيم المحفوظة لا تطابق نتيجة الحساب."
            ),
            frappe.ValidationError,
        )
    return values


def refresh_order_commercial_totals(order: Any, plan: Any) -> dict[str, Any]:
    """Refresh only DCO-owned quote totals that depend on Plan financials.

    Cutting Plan remains the sole owner of board/cutting/edge financial fields.
    The order stores only customer-facing commercial aggregates that belong to
    the order lifecycle itself.
    """

    settings = frappe.get_cached_doc("Almdina ERP Settings")
    pricing_settings = SpecialPricingSettings(
        design_fee_usd=flt(settings.default_special_design_fee_usd),
        cnc_fee_usd=flt(settings.default_special_cnc_fee_usd),
        manual_edge_fee_usd=flt(settings.default_special_manual_edge_fee_usd),
        margin_percent=flt(settings.default_special_margin_percent),
    )
    try:
        summary = calculate_special_pricing(
            (
                SpecialPricingPieceInput(
                    piece_type=str(piece.piece_type or "Regular"),
                    qty=cint(piece.qty),
                    area_m2=flt(piece.area_m2),
                    edge_cost_usd=flt(piece.edge_cost_usd),
                    price_status=str(piece.special_shape_price_status or ""),
                    approved_by=str(piece.special_shape_price_approved_by or ""),
                    custom_unit_price_usd=flt(piece.special_shape_custom_unit_price_usd),
                )
                for piece in (order.pieces or [])
            ),
            settings=pricing_settings,
            total_area_m2=flt(order.total_area_m2),
            board_and_cutting_cost_usd=(
                flt(plan.mdf_cost_usd) + flt(plan.cutting_cost_usd)
            ),
            total_cost_usd=flt(plan.total_cost_usd),
        )
    except CostingError as error:
        if str(error) == "special_shape_defaults_negative":
            frappe.throw(_("Special shape estimate defaults cannot be negative."))
        raise

    values = {
        "special_shapes_baseline_cost_usd": summary.baseline_cost_usd,
        "special_shapes_estimated_total_usd": summary.estimated_total_usd,
        "special_shapes_final_total_usd": summary.final_total_usd,
        "customer_quote_total_usd": summary.customer_quote_total_usd,
        "customer_quote_status": summary.customer_quote_status,
    }
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        values,
        update_modified=False,
    )
    for fieldname, value in values.items():
        setattr(order, fieldname, value)
    return values


def project_plan_costs_to_order(order: Any, plan: Any) -> dict[str, float]:
    """A6.2 compatibility facade: refresh order-owned quote totals only.

    The historical implementation copied every Plan financial field back onto
    Door Cutting Order. Runtime no longer needs that projection, so the function
    remains temporarily for older callers while deliberately performing no Plan
    financial mirror. It can be removed with the legacy surface after callers
    migrate to ``refresh_order_commercial_totals``.
    """

    refresh_order_commercial_totals(order, plan)
    return {}


def current_cost_plan(order: Any) -> Any | None:
    """Resolve financial reads from canonical Cutting Plan lineage only."""

    return current_working_plan(str(order.name))


def authoritative_cost_values(order: Any, *, plan: Any | None = None) -> dict[str, float]:
    """Return Plan-owned values with a read-only bridge for legacy A2 Drafts."""

    resolved_plan = plan if plan is not None else current_cost_plan(order)
    if resolved_plan is None:
        source = order
    elif (
        str(getattr(resolved_plan, "status", None) or "") == DRAFT
        and cint(getattr(resolved_plan, "cost_snapshot_version", 0)) < COST_SNAPSHOT_VERSION
    ):
        # A2 Draft plans had cost columns but did not own them. Until the first
        # A3 command adopts that Draft, the legacy DCO remains the safe read bridge.
        source = order
    else:
        source = resolved_plan
    return {fieldname: flt(getattr(source, fieldname, 0)) for fieldname in PLAN_COST_FIELDS}


def overlay_authoritative_costs(
    order: Any,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Overlay canonical Plan financials onto a DCO-shaped read model."""

    result = dict(snapshot)
    plan = current_cost_plan(order)
    result.update(authoritative_cost_values(order, plan=plan))
    if plan is not None:
        result["required_boards"] = int(plan.required_boards or 0)
    return result


__all__ = [
    "COST_SNAPSHOT_VERSION",
    "PLAN_COST_FIELDS",
    "apply_plan_costs",
    "authoritative_cost_values",
    "current_cost_plan",
    "initial_plan_cost_values",
    "initialize_draft_plan_cost_snapshot",
    "overlay_authoritative_costs",
    "persist_plan_cost_snapshot",
    "project_plan_costs_to_order",
    "refresh_order_commercial_totals",
]
