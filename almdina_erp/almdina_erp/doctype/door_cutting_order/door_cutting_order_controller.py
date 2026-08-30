from __future__ import annotations

from almdina_erp.almdina_erp.application.orders.process_order_save import process_order_save
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders import FrappeDoorCuttingOrderSaveGateway
from almdina_erp.almdina_erp.services.cutting_plan_invalidation_service import invalidate_stale_draft_plans
from almdina_erp.almdina_erp.services import new_order_recovery_service

from .door_cutting_order import DoorCuttingOrder


class DoorCuttingOrderController(DoorCuttingOrder):
    """Thin Frappe override controller for Door Cutting Order lifecycle."""

    def _gateway(self) -> FrappeDoorCuttingOrderSaveGateway:
        gateway = self.flags.get("_order_save_gateway")
        if gateway is None:
            gateway = FrappeDoorCuttingOrderSaveGateway(self)
            self.flags._order_save_gateway = gateway
        return gateway

    def validate(self) -> None:
        new_order_recovery_service.enforce_creation_identity_immutability(self)
        process_order_save(self._gateway())

    def before_insert(self) -> None:
        new_order_recovery_service.apply_new_order_creation_identity(self)

    def on_update(self) -> None:
        invalidate_stale_draft_plans(self)
        # Extra add-ons are order-owned commercial inputs. Refresh the quote after
        # persistence without creating, recalculating, or mutating Cutting Plan.
        refresh_order_commercial_totals(self)

    def ensure_special_shapes_documented(self) -> None:
        self._gateway().ensure_special_shapes_documented()

    def ensure_special_prices_approved(self) -> None:
        self._gateway().ensure_special_prices_approved()


__all__ = ["DoorCuttingOrderController"]
