from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.replacements.planning import (
    ReplacementPlanError,
    build_replacement_snapshot,
    calculate_edge_meters,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "almdina_erp"
HOOKS = ROOT / "hooks.py"
LEGACY_ENDPOINT = RUNTIME_ROOT / "services" / "legacy_endpoint_service.py"
REPLACEMENT_CANCELLATION = (
    RUNTIME_ROOT / "services" / "replacement_cancellation_service.py"
)
LEGACY_CANCELLATION_MODULE = (
    "almdina_erp.almdina_erp.services.replacement_cancellation_service"
)
RETIRED_PRODUCT_MODULES = {
    "almdina_erp.almdina_erp.services.actual_consumption_reversal": RUNTIME_ROOT / "services" / "actual_consumption_reversal.py",
    "almdina_erp.almdina_erp.services.actual_consumption_service": RUNTIME_ROOT / "services" / "actual_consumption_service.py",
    "almdina_erp.almdina_erp.services.performance_service": RUNTIME_ROOT / "services" / "performance_service.py",
    "almdina_erp.almdina_erp.services.preflight_service": RUNTIME_ROOT / "services" / "preflight_service.py",
    "almdina_erp.almdina_erp.services.remnant_service": RUNTIME_ROOT / "services" / "remnant_service.py",
    "almdina_erp.almdina_erp.services.settings_access_service": RUNTIME_ROOT / "services" / "settings_access_service.py",
    "almdina_erp.almdina_erp.services.stock_availability_service": RUNTIME_ROOT / "services" / "stock_availability_service.py",
    "almdina_erp.almdina_erp.services.stock_service": RUNTIME_ROOT / "services" / "stock_service.py",
}
RETIRED_GATEWAYS = {
    "almdina_erp.almdina_erp.infrastructure.frappe.stock_execution_gateway": RUNTIME_ROOT / "infrastructure" / "frappe" / "stock_execution_gateway.py",
    "almdina_erp.almdina_erp.infrastructure.frappe.remnant_execution_gateway": RUNTIME_ROOT / "infrastructure" / "frappe" / "remnant_execution_gateway.py",
}


def _snapshot(**overrides):
    values = {
        "board_description": "MDF أبيض 18 مم",
        "board_width_cm": 207,
        "board_length_cm": 280,
        "trim_margin_mm": 5,
        "kerf_mm": 3,
        "original_piece_label": "2.3",
        "piece_width_cm": 50,
        "piece_length_cm": 90,
        "allow_rotation": False,
        "edge_long_right": True,
        "edge_long_left": False,
        "edge_width_top": True,
        "edge_width_bottom": False,
        "edge_type": "قشاط 2سم عادي",
        "notes": "",
    }
    values.update(overrides)
    return build_replacement_snapshot(**values)


class TestReplacementPlanning(unittest.TestCase):
    def test_snapshot_always_uses_one_full_board(self) -> None:
        plan = _snapshot()

        self.assertEqual(plan["required_full_boards"], 1)
        self.assertEqual(plan["sheets"][0]["source_type"], "Full Board")
        self.assertEqual(
            plan["sheets"][0]["board_description"],
            "MDF أبيض 18 مم",
        )
        self.assertEqual(len(plan["sheets"]), 1)
        self.assertEqual(len(plan["sheets"][0]["pieces"]), 1)

    def test_rotation_occurs_only_when_explicitly_allowed(self) -> None:
        plan = _snapshot(
            board_width_cm=91,
            board_length_cm=51,
            allow_rotation=True,
        )
        piece = plan["sheets"][0]["pieces"][0]

        self.assertTrue(piece["rotated"])
        self.assertEqual(piece["w"], 90)
        self.assertEqual(piece["h"], 50)

        with self.assertRaises(ReplacementPlanError):
            _snapshot(
                board_width_cm=91,
                board_length_cm=51,
                allow_rotation=False,
            )

    def test_trim_margin_can_make_a_piece_invalid(self) -> None:
        with self.assertRaises(ReplacementPlanError):
            _snapshot(
                board_width_cm=50,
                board_length_cm=90,
                trim_margin_mm=5,
            )

    def test_snapshot_preserves_edge_flags(self) -> None:
        piece = _snapshot()["sheets"][0]["pieces"][0]

        self.assertEqual(piece["edge_long_right"], 1)
        self.assertEqual(piece["edge_long_left"], 0)
        self.assertEqual(piece["edge_width_top"], 1)
        self.assertEqual(piece["edge_width_bottom"], 0)
        self.assertEqual(piece["edge_type"], "قشاط 2سم عادي")

    def test_edge_meter_calculation_is_pure(self) -> None:
        meters = calculate_edge_meters(
            width_cm=50,
            length_cm=90,
            edge_long_right=True,
            edge_long_left=False,
            edge_width_top=True,
            edge_width_bottom=False,
        )

        self.assertEqual(meters, 1.4)

    def test_snapshot_contains_no_inventory_identity(self) -> None:
        source = json.dumps(_snapshot(), ensure_ascii=False).lower()
        for token in (
            "board_item",
            "warehouse",
            "stock",
            "reservation",
            "remnant",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_legacy_cancellation_route_has_no_internal_runtime_consumers(self) -> None:
        self.assertFalse(REPLACEMENT_CANCELLATION.exists())

        offenders: list[str] = []
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            if LEGACY_CANCELLATION_MODULE in source:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [], "\n".join(offenders))

        hooks = HOOKS.read_text(encoding="utf-8")
        legacy_endpoint = LEGACY_ENDPOINT.read_text(encoding="utf-8")
        self.assertIn(
            f'"{LEGACY_CANCELLATION_MODULE}.cancel_replacement"',
            hooks,
        )
        self.assertIn("legacy_endpoint_service.cancel_legacy_replacement", hooks)
        self.assertIn("def cancel_legacy_replacement", legacy_endpoint)
        self.assertIn("reverse_stock", legacy_endpoint)
        self.assertIn("replacement_service", legacy_endpoint)

    def test_retired_stock_and_remnant_implementations_are_absent(self) -> None:
        retired = {**RETIRED_PRODUCT_MODULES, **RETIRED_GATEWAYS}
        for path in retired.values():
            self.assertFalse(path.exists(), path)

        offenders: list[str] = []
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for module in retired:
                if module in source:
                    offenders.append(f"{path.relative_to(ROOT)} -> {module}")
        self.assertEqual(offenders, [], "\n".join(offenders))

        hooks = HOOKS.read_text(encoding="utf-8")
        legacy_endpoint = LEGACY_ENDPOINT.read_text(encoding="utf-8")
        for module in RETIRED_PRODUCT_MODULES:
            self.assertIn(f'"{module}.', hooks)
        self.assertIn("legacy_endpoint_service.retired_product_endpoint", hooks)
        self.assertIn("def retired_product_endpoint", legacy_endpoint)

    def test_revision_activation_keeps_material_safety_without_stock_side_effects(self) -> None:
        source = (
            RUNTIME_ROOT / "services" / "order_revision_activation.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _has_material_activity", source)
        self.assertIn("predecessor_has_material_activity", source)
        self.assertNotIn("transition_order_reservation", source)
        self.assertNotIn("Board Remnant", source)
        self.assertIn("released_material_reservations=()", source)
        self.assertIn("released_remnants=()", source)

    def test_stock_availability_report_is_fully_retired(self) -> None:
        report_dir = RUNTIME_ROOT / "report" / "order_stock_availability"
        self.assertFalse(report_dir.exists())


if __name__ == "__main__":
    unittest.main()
