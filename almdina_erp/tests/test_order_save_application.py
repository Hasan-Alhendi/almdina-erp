from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.orders.process_order_save import (
    process_order_save,
)


class FakeOrderSaveGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enforce_immutability(self) -> None:
        self.calls.append("enforce_immutability")

    def set_piece_numbers(self) -> None:
        self.calls.append("set_piece_numbers")

    def validate_piece_inputs(self) -> None:
        self.calls.append("validate_piece_inputs")

    def validate_piece_policies(self) -> None:
        self.calls.append("validate_piece_policies")

    def load_board_snapshot(self) -> None:
        self.calls.append("load_board_snapshot")

    def calculate_cut_dimensions(self) -> None:
        self.calls.append("calculate_cut_dimensions")

    def calculate_piece_costs(self) -> None:
        self.calls.append("calculate_piece_costs")


class ExplodingPlanGateway(FakeOrderSaveGateway):
    """Legacy plan methods must never be reached by ordinary order save."""

    def __getattr__(self, name: str):
        if any(
            token in name
            for token in (
                "plan",
                "fingerprint",
                "recalculation",
                "reuse",
                "snapshot",
                "cutting_plan",
            )
        ):
            raise AssertionError(f"order save reached retired plan method: {name}")
        raise AttributeError(name)


class TestOrderSaveApplication(unittest.TestCase):
    def test_validation_and_piece_derivation_order_is_stable(self) -> None:
        gateway = FakeOrderSaveGateway()
        outcome = process_order_save(gateway)

        self.assertIsNone(outcome)
        self.assertEqual(
            gateway.calls,
            [
                "enforce_immutability",
                "set_piece_numbers",
                "validate_piece_inputs",
                "validate_piece_policies",
                "load_board_snapshot",
                "calculate_cut_dimensions",
                "calculate_piece_costs",
            ],
        )

    def test_order_save_never_queries_or_mutates_cutting_plan_state(self) -> None:
        gateway = ExplodingPlanGateway()
        process_order_save(gateway)

        self.assertEqual(
            gateway.calls[-3:],
            [
                "load_board_snapshot",
                "calculate_cut_dimensions",
                "calculate_piece_costs",
            ],
        )


if __name__ == "__main__":
    unittest.main()
