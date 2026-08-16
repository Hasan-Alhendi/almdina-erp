from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.application.cutting.version import ENGINE_VERSION
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot_json,
)

from .costing_adapter import FrappeOrderCostingAdapter
from .cut_dimension_adapter import FrappeOrderCutDimensionAdapter
from .cut_dimension_plan_adapter import FrappeCutDimensionPlanAdapter
from .document_access import FrappeOrderDocumentAccess
from .edge_profile_repository import FrappeEdgeProfileRepository
from .piece_policy_adapter import FrappeOrderPiecePolicyAdapter


_PLAN_JSON_FIELDS = (
    "cutting_plan_json",
    "system_plan_json",
    "custom_plan_json",
)


class FrappeDoorCuttingOrderSaveGateway:
    """Frappe implementation of the order-save Application port."""

    def __init__(self, document: Any) -> None:
        self.document = document
        self.access = FrappeOrderDocumentAccess(document)
        self.edge_profiles = FrappeEdgeProfileRepository(document)
        self.piece_policy = FrappeOrderPiecePolicyAdapter(
            document,
            self.access,
        )
        self.cut_dimensions = FrappeOrderCutDimensionAdapter(
            document,
            self.edge_profiles,
        )
        self.costing = FrappeOrderCostingAdapter(
            document,
            self.access,
            self.edge_profiles,
            engine_version=ENGINE_VERSION,
        )
        self.plan = FrappeCutDimensionPlanAdapter(
            document,
            self.access,
            self.costing,
        )

    def enforce_immutability(self) -> None:
        self.access.enforce_immutability()

    def set_piece_numbers(self) -> None:
        self.access.set_piece_numbers()

    def validate_numeric_inputs(self) -> None:
        self.access.validate_numeric_inputs()

    def validate_piece_inputs(self) -> None:
        self.access.validate_piece_inputs()

    def validate_piece_policies(self) -> None:
        self.piece_policy.validate_rows()

    def load_board_snapshot(self) -> None:
        self.access.load_board_snapshot()

    def calculate_cut_dimensions(self) -> None:
        self.cut_dimensions.calculate_rows()

    def calculate_piece_costs(self) -> None:
        self.costing.calculate_piece_rows()

    def plan_input_fingerprint(self) -> str:
        return self.plan.plan_input_fingerprint()

    def force_recalculation_requested(self) -> bool:
        return bool(
            self.document.flags.get("force_cutting_plan_recalculation")
        )

    def can_reuse_current_plan(self, input_fingerprint: str) -> bool:
        return self.plan.can_reuse_current_plan(input_fingerprint)

    def calculate_cutting_plan(self, input_fingerprint: str) -> None:
        self.plan.calculate_cutting_plan(input_fingerprint)

    def refresh_current_plan(self, input_fingerprint: str) -> None:
        self.plan.refresh_current_plan(input_fingerprint)

    def invalidate_current_plan(self) -> None:
        self.plan.invalidate_current_plan()

    def sanitize_plan_snapshots(self) -> None:
        """Keep every order plan field inside the non-financial JSON contract."""

        for fieldname in _PLAN_JSON_FIELDS:
            if not self.document.meta.has_field(fieldname):
                continue
            current = getattr(self.document, fieldname, None)
            if current in (None, ""):
                continue
            setattr(
                self.document,
                fieldname,
                sanitize_plan_snapshot_json(current),
            )

    def ensure_special_shapes_documented(self) -> None:
        self.piece_policy.ensure_documented()

    def ensure_special_prices_approved(self) -> None:
        self.piece_policy.ensure_prices_approved()


__all__ = ["FrappeDoorCuttingOrderSaveGateway"]
