from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.application.cutting.version import ENGINE_VERSION

from .board_input_adapter import FrappeOrderBoardInputAdapter
from .costing_adapter import FrappeOrderCostingAdapter
from .cut_dimension_adapter import FrappeOrderCutDimensionAdapter
from .document_access import FrappeOrderDocumentAccess
from .edge_profile_repository import FrappeEdgeProfileRepository
from .piece_policy_adapter import FrappeOrderPiecePolicyAdapter


class FrappeDoorCuttingOrderSaveGateway:
    """Frappe implementation of the customer-order save Application port.

    This gateway intentionally has no Cutting Plan adapter. It validates and
    derives order-owned requirements only; plan invalidation is a separate
    post-persistence use case owned by the Cutting Plan boundary.
    """

    def __init__(self, document: Any) -> None:
        self.document = document
        self.access = FrappeOrderDocumentAccess(document)
        self.board = FrappeOrderBoardInputAdapter(document, self.access)
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

    def enforce_immutability(self) -> None:
        self.access.enforce_immutability()

    def set_piece_numbers(self) -> None:
        self.access.set_piece_numbers()

    def validate_piece_inputs(self) -> None:
        self.access.validate_piece_inputs()

    def validate_piece_policies(self) -> None:
        self.piece_policy.validate_rows()

    def load_board_snapshot(self) -> None:
        self.board.load_snapshot()

    def calculate_cut_dimensions(self) -> None:
        self.cut_dimensions.calculate_rows()

    def calculate_piece_costs(self) -> None:
        self.costing.calculate_piece_rows()

    def ensure_special_shapes_documented(self) -> None:
        self.piece_policy.ensure_documented()

    def ensure_special_prices_approved(self) -> None:
        self.piece_policy.ensure_prices_approved()


__all__ = ["FrappeDoorCuttingOrderSaveGateway"]
