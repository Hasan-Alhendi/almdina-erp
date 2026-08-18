from __future__ import annotations

from almdina_erp.almdina_erp.application.orders.process_order_save import (
    process_order_save,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders import (
    FrappeDoorCuttingOrderSaveGateway,
)

from .door_cutting_order import DoorCuttingOrder


class DoorCuttingOrderController(DoorCuttingOrder):
    """Thin Frappe override controller for Door Cutting Order.

    Frappe lifecycle entry points stay here. Ordinary validation owns customer
    requirements only; the post-persistence hook notifies the Cutting Plan
    boundary that existing Draft revisions may have become stale.
    """

    def _gateway(self) -> FrappeDoorCuttingOrderSaveGateway:
        gateway = self.flags.get("_order_save_gateway")
        if gateway is None:
            gateway = FrappeDoorCuttingOrderSaveGateway(self)
            self.flags._order_save_gateway = gateway
        return gateway

    def validate(self) -> None:
        process_order_save(self._gateway())

    def on_update(self) -> None:
        from almdina_erp.almdina_erp.services.cutting_plan_invalidation_service import (
            invalidate_stale_draft_plans,
        )

        invalidate_stale_draft_plans(self)

    def ensure_special_shapes_documented(self) -> None:
        self._gateway().ensure_special_shapes_documented()

    def ensure_special_prices_approved(self) -> None:
        self._gateway().ensure_special_prices_approved()


__all__ = ["DoorCuttingOrderController"]
