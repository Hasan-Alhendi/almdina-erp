from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import APPROVED, DRAFT, SYSTEM
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    PLAN_COST_FIELDS,
    apply_plan_costs,
    current_cost_plan,
    factory_execution_edge_cost,
    initialize_draft_plan_cost_snapshot,
    persist_plan_cost_snapshot,
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.domain.cutting.physical_execution_contract import physical_execution_for_snapshot


def _assert_cost_inputs_persisted(
    plan: Any,
    *,
    board_rate_usd: float,
    cutting_cost_per_board_usd: float,
    offcut_price_usd: float | None = None,
) -> None:
    """Fail closed if Frappe discarded protected financial field mutations."""

    persisted = frappe.db.get_value(
        "Cutting Plan",
        plan.name,
        ["board_rate_usd", "cutting_cost_per_board_usd", "offcut_price_usd"],
        as_dict=True,
    ) or {}
    actual_board_rate = flt(persisted.get("board_rate_usd"))
    actual_cutting_rate = flt(persisted.get("cutting_cost_per_board_usd"))
    expected_board_rate = flt(board_rate_usd)
    expected_cutting_rate = flt(cutting_cost_per_board_usd)
    expected_offcut_price = flt(offcut_price_usd)

    if (
        actual_board_rate != expected_board_rate
        or actual_cutting_rate != expected_cutting_rate
        or flt(persisted.get("offcut_price_usd")) != expected_offcut_price
    ):
        frappe.throw(
            _(
                "تعذر حفظ إعدادات التكلفة على خطة القص. "
                "أوقف النظام العملية لأن القيم المحفوظة لا تطابق القيم المدخلة."
            ),
            frappe.ValidationError,
        )


def update_plan_cost_settings(
    order: Any,
    *,
    board_rate_usd: float,
    cutting_cost_per_board_usd: float,
    offcut_price_usd: float | None = None,
) -> dict[str, Any]:
    """Update only plan-owned cost inputs and their derived financial result.

    Geometry, fingerprints, validation status, and recalculation state are not
    touched. A6.2 keeps Plan financials exclusively on Cutting Plan and refreshes
    only the customer-facing commercial aggregates that are owned by the order.
    """

    require_cutting_plan_capability(
        order,
        Capability.EDIT_COST_SETTINGS,
        message=_("لا تملك صلاحية تعديل إعدادات تكلفة خطة القص لهذا الطلب."),
    )
    plan = current_cost_plan(order)
    if plan is None:
        frappe.throw(
            _("لا توجد خطة قص يمكن حفظ إعدادات التكلفة عليها."),
            frappe.ValidationError,
        )

    initialize_draft_plan_cost_snapshot(order, plan)
    plan.board_rate_usd = flt(board_rate_usd)
    plan.cutting_cost_per_board_usd = flt(cutting_cost_per_board_usd)
    requested_offcut_price = flt(offcut_price_usd)
    if requested_offcut_price < 0:
        frappe.throw(_("سعر الفضلة لا يمكن أن يكون سالبًا."), frappe.ValidationError)
    snapshot = frappe.parse_json(getattr(plan, "snapshot_json", None) or "{}") or {}
    projection = physical_execution_for_snapshot(snapshot)
    if requested_offcut_price and (projection is None or not projection.has_factory_source_offcut):
        frappe.throw(
            _("سعر الفضلة يُستخدم فقط عندما يكون المصدر والتنفيذ من المعمل."),
            frappe.ValidationError,
        )
    # Reclassification removes the only eligible state => price must not survive
    # as a stale commercial charge.  An omitted value keeps the applicable price.
    if projection is None:
        # A historical plan has no OFFCUT contract.  Preserve its stored
        # commercial history instead of silently rewriting it during costing.
        plan.offcut_price_usd = flt(getattr(plan, "offcut_price_usd", 0))
    else:
        plan.offcut_price_usd = (
            requested_offcut_price
            if offcut_price_usd is not None and projection.has_factory_source_offcut
            else (flt(plan.offcut_price_usd) if projection.has_factory_source_offcut else 0)
        )
    plan.edge_cost_usd = factory_execution_edge_cost(order, plan)
    apply_plan_costs(plan)
    status = str(getattr(plan, "status", None) or "")
    if status == DRAFT:
        repository = FrappeCuttingPlanCommandRepository(Capability.EDIT_COST_SETTINGS)
        repository.save_document(plan)
    elif status == APPROVED:
        persist_plan_cost_snapshot(plan)
    else:
        frappe.throw(
            _("لا يمكن حفظ إعدادات التكلفة على خطة في حالة {0}.").format(status),
            frappe.ValidationError,
        )
    _assert_cost_inputs_persisted(
        plan,
        board_rate_usd=board_rate_usd,
        cutting_cost_per_board_usd=cutting_cost_per_board_usd,
        offcut_price_usd=plan.offcut_price_usd,
    )
    refresh_order_commercial_totals(order, plan)

    return {
        "order_name": order.name,
        "cutting_plan": plan.name,
        "plan_source_type": str(plan.source_type or SYSTEM),
        "cost_snapshot_version": int(plan.cost_snapshot_version or 0),
        **{
            fieldname: flt(getattr(plan, fieldname, 0))
            for fieldname in PLAN_COST_FIELDS
        },
    }


__all__ = ["update_plan_cost_settings"]
