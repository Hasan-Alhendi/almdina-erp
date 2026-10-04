from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.cutting import (
    PACKING_OPTIONS,
    STRATEGIES,
    auto_fast,
    expand_piece_groups,
    get_strategy,
    run_single_method,
    validate_plan,
)


class TestCuttingDomainStrategies(unittest.TestCase):
    @staticmethod
    def _pieces() -> list[dict[str, object]]:
        return expand_piece_groups(
            [
                {
                    "width_cm": 60,
                    "length_cm": 80,
                    "qty": 2,
                    "allow_rotation": 1,
                    "piece_type": "Regular",
                },
                {
                    "width_cm": 40,
                    "length_cm": 100,
                    "qty": 1,
                    "allow_rotation": 1,
                    "piece_type": "Clipped Corner",
                    "clipped_corner_position": "Top Right",
                    "clipped_corner_width_cm": 8,
                    "clipped_corner_length_cm": 12,
                },
            ]
        )

    def test_registry_exposes_each_manual_option_once(self) -> None:
        keys = [strategy.key for strategy in STRATEGIES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(PACKING_OPTIONS, ("Auto", *keys))
        self.assertGreaterEqual(len(keys), 17)

    def test_every_strategy_produces_a_valid_plan(self) -> None:
        pieces = self._pieces()
        for strategy in STRATEGIES:
            with self.subTest(strategy=strategy.key):
                plan = strategy.execute(pieces, 122, 244, 0.4)
                self.assertFalse(plan["unplaced"])
                self.assertTrue(plan["sheets"])
                self.assertEqual(plan["method_key"], strategy.key)
                self.assertEqual(validate_plan(plan, pieces, 122, 244), [])

    def test_unknown_manual_method_uses_stable_maxrects_fallback(self) -> None:
        strategy = get_strategy("Unknown Strategy")
        self.assertEqual(strategy.key, "MaxRects Best Short Side")

    def test_panel_saw_auto_fast_chooses_guillotine_family(self) -> None:
        plan = auto_fast(
            self._pieces(),
            122,
            244,
            0.4,
            machine_type="Panel Saw",
        )
        self.assertTrue(plan["method_key"].startswith("Guillotine"))
        self.assertEqual(plan["optimization_mode"], "Auto")

    def test_domain_methods_are_the_canonical_cutting_entry_points(self) -> None:
        domain_plan = run_single_method(
            self._pieces(),
            122,
            244,
            0.4,
            "MaxRects Best Area",
        )
        self.assertEqual(domain_plan["method_key"], "MaxRects Best Area")
        self.assertEqual(validate_plan(domain_plan, self._pieces(), 122, 244), [])


if __name__ == "__main__":
    unittest.main()
