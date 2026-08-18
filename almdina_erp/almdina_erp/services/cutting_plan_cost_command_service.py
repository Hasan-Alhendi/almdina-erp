from __future__ import annotations

from typing import Any

from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import SYSTEM, UPLOADED_DXF
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
    initialize_draft_plan_cost_snapshot,
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    current_working_plan,
)


def _current_source_type(order: Any) -> str:
    plan = current_working_plan(str(order.name))
    source_type = str(getattr(plan, "source_type", None) or SYSTEM) if plan else SYSTEM
    return UPLOADED_DXF if source_type == UPLOADED_DXF else SYSTEM


def update_plan_cost_settings(
    order: Any,
    *,
    board_rate_usd: float,
    cutting_cost_per_board_usd: float,
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
    repository = FrappeCuttingPlanCommandRepository(Capability.EDIT_COST_SETTINGS)
    plan = (
        repository.ensure_uploaded_dxf_draft(order)
        if _current_source_type(order) == UPLOADED_DXF
        else repository.ensure_system_draft(order)
    )
    initialize_draft_plan_cost_snapshot(order, plan)
    plan.board_rate_usd = flt(board_rate_usd)
    plan.cutting_cost_per_board_usd = flt(cutting_cost_per_board_usd)
    apply_plan_costs(plan)
    repository.save_document(plan)
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
