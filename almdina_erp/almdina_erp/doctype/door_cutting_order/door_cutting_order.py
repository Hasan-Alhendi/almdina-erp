from __future__ import annotations

from typing import Any

import frappe
from frappe.model.document import Document

from almdina_erp.almdina_erp.application.orders.process_order_save import (
    process_order_save,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders import (
    FrappeDoorCuttingOrderSaveGateway,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.document_access import (
    FrappeOrderDocumentAccess,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.plan_adapter import (
    FrappeOrderPlanAdapter,
)


class DoorCuttingOrder(Document):
    """Canonical Frappe DocType base with thin compatibility delegates.

    Frappe requires the active ``override_doctype_class`` controller to subclass
    this canonical DocType class. Business validation, cutting, costing, and plan
    ownership live in Application/Domain/Infrastructure; this class only keeps
    the framework base plus a small set of historical helper signatures still
    used by preview/simulation paths while they migrate independently.
    """

    def _gateway(self) -> FrappeDoorCuttingOrderSaveGateway:
        gateway = self.flags.get("_order_save_gateway")
        if gateway is None:
            gateway = FrappeDoorCuttingOrderSaveGateway(self)
            self.flags._order_save_gateway = gateway
        return gateway

    def _legacy_plan_adapter(self) -> FrappeOrderPlanAdapter:
        adapter = self.flags.get("_legacy_order_plan_adapter")
        if adapter is None:
            gateway = self._gateway()
            # Historical preview/simulation helpers planned from the entered
            # dimensions. Keep that compatibility contract while delegating the
            # actual plan work to the canonical focused adapter.
            adapter = FrappeOrderPlanAdapter(
                self,
                gateway.access,
                gateway.costing,
            )
            self.flags._legacy_order_plan_adapter = adapter
        return adapter

    def validate(self) -> None:
        process_order_save(self._gateway())

    def _get_old_doc(self) -> Any | None:
        return self._gateway().access.old_document()

    @staticmethod
    def _get_settings() -> Any:
        return frappe.get_cached_doc("Almdina ERP Settings")

    @staticmethod
    def _finite(value: Any, label: str) -> float:
        return FrappeOrderDocumentAccess.finite(value, label)

    def _enforce_approved_immutability(self) -> None:
        self._gateway().enforce_immutability()

    def _set_piece_numbers(self) -> None:
        self._gateway().set_piece_numbers()

    def _validate_numeric_inputs(self) -> None:
        self._gateway().validate_numeric_inputs()

    def _validate_piece_inputs(self) -> None:
        self._gateway().validate_piece_inputs()

    def _validate_special_shape_rows(self) -> None:
        self._gateway().validate_piece_policies()

    def _load_board_snapshot(self) -> None:
        self._gateway().load_board_snapshot()

    def _get_edge_rate_map(self) -> dict[str, float]:
        return self._gateway().edge_profiles.rate_map()

    def _calculate_piece_rows(self) -> None:
        self._gateway().calculate_piece_costs()

    @staticmethod
    def _normalized_number(value: Any) -> float:
        return FrappeOrderDocumentAccess.normalized_number(value)

    def _plan_input_fingerprint(
        self,
        settings: Any | None = None,
        source: Any | None = None,
    ) -> str:
        del settings
        if source is not None and source is not self:
            source_gateway = FrappeDoorCuttingOrderSaveGateway(source)
            return FrappeOrderPlanAdapter(
                source,
                source_gateway.access,
                source_gateway.costing,
            ).plan_input_fingerprint()
        return self._legacy_plan_adapter().plan_input_fingerprint()

    def _parse_plan_snapshot(self) -> dict[str, Any]:
        return self._gateway().access.parse_plan_snapshot()

    def _can_reuse_current_plan(
        self,
        input_fingerprint: str,
        settings: Any | None = None,
    ) -> bool:
        del settings
        return self._legacy_plan_adapter().can_reuse_current_plan(
            input_fingerprint
        )

    def _set_cutting_plan_json(self, snapshot: dict[str, Any] | str) -> None:
        self._gateway().access.set_plan_snapshot(snapshot)

    def _refresh_costs_from_plan(
        self,
        settings: Any,
        snapshot: dict[str, Any],
    ) -> None:
        del settings
        self._gateway().costing.refresh_from_plan(snapshot)

    def _refresh_current_plan_without_optimization(
        self,
        settings: Any,
        input_fingerprint: str,
    ) -> None:
        del settings
        self._legacy_plan_adapter().refresh_current_plan(input_fingerprint)

    def _mark_plan_for_recalculation(self, settings: Any) -> None:
        del settings
        self._legacy_plan_adapter().invalidate_current_plan()

    def _calculate_cutting_plan(
        self,
        settings: Any,
        input_fingerprint: str,
    ) -> None:
        del settings
        self._legacy_plan_adapter().calculate_cutting_plan(input_fingerprint)

    def _calculate_special_shape_pricing(self, settings: Any) -> None:
        del settings
        self._gateway().costing.calculate_special_shape_pricing()

    def ensure_special_shapes_documented(self) -> None:
        self._gateway().ensure_special_shapes_documented()

    def ensure_special_prices_approved(self) -> None:
        self._gateway().ensure_special_prices_approved()

    @staticmethod
    def _piece_row_as_dict(row: Any) -> dict[str, Any]:
        return FrappeOrderPlanAdapter.piece_row_as_dict(row)


@frappe.whitelist()
def recalculate_order(order_name: str) -> dict[str, Any]:
    """Compatibility delegate for the historical DocType RPC path."""

    from almdina_erp.almdina_erp.services.order_plan_permission_service import (
        recalculate_order as recalculate,
    )

    return recalculate(order_name)


__all__ = ["DoorCuttingOrder", "recalculate_order"]
