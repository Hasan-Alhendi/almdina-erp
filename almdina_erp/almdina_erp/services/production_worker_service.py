from __future__ import annotations

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.shop_floor.commands import (
    ShopFloorCommandError,
    ShopFloorPermissionDenied,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_command_repository import (
    FrappeShopFloorCommandRepository,
)


_repository = FrappeShopFloorCommandRepository()


@frappe.whitelist()
def get_reassignment_workers(stage_name: str) -> list[dict[str, str]]:
    stage = _repository.get_stage_state(stage_name)
    order = _repository.get_order_state(stage.order_name)
    decision = decide_production_action(
        Capability.REASSIGN_WORKER,
        capabilities=_repository.capabilities_for_order(order.name),
        facts=ProductionActionFacts(
            order_status=order.status,
            production_path=order.production_path,
            current_stage_name=order.current_stage,
            has_cutting_plan=order.has_cutting_plan,
            plan_needs_recalculation=order.plan_needs_recalculation,
            stage_name=stage.name,
            stage_type=stage.stage_type,
            stage_status=stage.status,
            assigned_to=stage.assigned_to,
            actor=_repository.current_user(),
            drawing_dxf_status=order.drawing_dxf_status,
        ),
    )
    if not decision.allowed:
        if decision.code == "missing_capability":
            raise ShopFloorPermissionDenied(_(decision.reason))
        raise ShopFloorCommandError(_(decision.reason))
    return _repository.get_users_for_stage(stage.stage_type)


__all__ = ["get_reassignment_workers"]
