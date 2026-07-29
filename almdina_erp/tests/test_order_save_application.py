from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.orders.process_order_save import (
    process_order_save,
)


class FakeOrderSaveGateway:
    def __init__(self, *, force: bool = False, reuse: bool = False) -> None:
        self.force = force
        self.reuse = reuse
        self.calls: list[str] = []

    def enforce_immutability(self) -> None:
        self.calls.append("enforce_immutability")

    def set_piece_numbers(self) -> None:
        self.calls.append("set_piece_numbers")

    def validate_numeric_inputs(self) -> None:
        self.calls.append("validate_numeric_inputs")

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

    def plan_input_fingerprint(self) -> str:
        self.calls.append("plan_input_fingerprint")
        return "fingerprint"

    def force_recalculation_requested(self) -> bool:
        self.calls.append("force_recalculation_requested")
        return self.force

    def can_reuse_current_plan(self, input_fingerprint: str) -> bool:
        self.calls.append(f"can_reuse_current_plan:{input_fingerprint}")
        return self.reuse

    def calculate_cutting_plan(self, input_fingerprint: str) -> None:
        self.calls.append(f"calculate_cutting_plan:{input_fingerprint}")

    def refresh_current_plan(self, input_fingerprint: str) -> None:
        self.calls.append(f"refresh_current_plan:{input_fingerprint}")

    def invalidate_current_plan(self) -> None:
        self.calls.append("invalidate_current_plan")


class TestOrderSaveApplication(unittest.TestCase):
    def test_forced_recalculation_skips_reuse_probe(self) -> None:
        gateway = FakeOrderSaveGateway(force=True, reuse=True)
        outcome = process_order_save(gateway)

        self.assertEqual(outcome.plan_action, "recalculated")
        self.assertIn("calculate_cutting_plan:fingerprint", gateway.calls)
        self.assertNotIn("can_reuse_current_plan:fingerprint", gateway.calls)
        self.assertNotIn("refresh_current_plan:fingerprint", gateway.calls)
        self.assertNotIn("invalidate_current_plan", gateway.calls)

    def test_reusable_plan_refreshes_without_optimization(self) -> None:
        gateway = FakeOrderSaveGateway(reuse=True)
        outcome = process_order_save(gateway)

        self.assertEqual(outcome.plan_action, "reused")
        self.assertIn("can_reuse_current_plan:fingerprint", gateway.calls)
        self.assertIn("refresh_current_plan:fingerprint", gateway.calls)
        self.assertNotIn("calculate_cutting_plan:fingerprint", gateway.calls)
        self.assertNotIn("invalidate_current_plan", gateway.calls)

    def test_stale_plan_is_invalidated(self) -> None:
        gateway = FakeOrderSaveGateway()
        outcome = process_order_save(gateway)

        self.assertEqual(outcome.plan_action, "invalidated")
        self.assertIn("invalidate_current_plan", gateway.calls)
        self.assertNotIn("calculate_cutting_plan:fingerprint", gateway.calls)
        self.assertNotIn("refresh_current_plan:fingerprint", gateway.calls)

    def test_validation_and_piece_calculation_order_is_stable(self) -> None:
        gateway = FakeOrderSaveGateway()
        process_order_save(gateway)

        self.assertEqual(
            gateway.calls[:9],
            [
                "enforce_immutability",
                "set_piece_numbers",
                "validate_numeric_inputs",
                "validate_piece_inputs",
                "validate_piece_policies",
                "load_board_snapshot",
                "calculate_cut_dimensions",
                "calculate_piece_costs",
                "plan_input_fingerprint",
            ],
        )


if __name__ == "__main__":
    unittest.main()
