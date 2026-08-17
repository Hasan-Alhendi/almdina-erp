from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.orders.costing import calculate_order_costs


@dataclass(frozen=True, slots=True)
class CostingInputs:
    required_boards: int
    board_rate_usd: float
    cutting_cost_per_board_usd: float
    edge_cost_usd: float
    special_shape_total_usd: float = 0.0
    internal_loss_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class CostingSnapshot:
    required_boards: int
    board_rate_usd: float
    cutting_cost_per_board_usd: float
    board_cost_usd: float
    cutting_cost_usd: float
    edge_cost_usd: float
    special_shape_total_usd: float
    operational_cost_usd: float
    customer_quote_total_usd: float
    internal_loss_cost_usd: float
    actual_cost_usd: float


def calculate_costing_snapshot(inputs: CostingInputs) -> CostingSnapshot:
    operational = calculate_order_costs(
        required_boards=max(0, int(inputs.required_boards)),
        board_rate_usd=max(0.0, float(inputs.board_rate_usd)),
        cutting_cost_per_board_usd=max(
            0.0,
            float(inputs.cutting_cost_per_board_usd),
        ),
        edge_cost_usd=max(0.0, float(inputs.edge_cost_usd)),
    )
    special_total = max(0.0, float(inputs.special_shape_total_usd))
    internal_loss = max(0.0, float(inputs.internal_loss_cost_usd))
    customer_quote = operational.total_cost_usd + special_total
    actual = operational.total_cost_usd + internal_loss
    return CostingSnapshot(
        required_boards=operational.required_boards,
        board_rate_usd=max(0.0, float(inputs.board_rate_usd)),
        cutting_cost_per_board_usd=max(
            0.0,
            float(inputs.cutting_cost_per_board_usd),
        ),
        board_cost_usd=operational.mdf_cost_usd,
        cutting_cost_usd=operational.cutting_cost_usd,
        edge_cost_usd=operational.edge_cost_usd,
        special_shape_total_usd=special_total,
        operational_cost_usd=operational.total_cost_usd,
        customer_quote_total_usd=customer_quote,
        internal_loss_cost_usd=internal_loss,
        actual_cost_usd=actual,
    )


__all__ = [
    "CostingInputs",
    "CostingSnapshot",
    "calculate_costing_snapshot",
]
