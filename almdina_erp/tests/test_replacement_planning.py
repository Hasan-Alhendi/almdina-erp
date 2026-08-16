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
LEGACY_STOCK_MODULES = {
    "almdina_erp.almdina_erp.services.stock_actual_service": RUNTIME_ROOT / "services" / "stock_actual_service.py",
    "almdina_erp.almdina_erp.services.stock_reconciliation_service": RUNTIME_ROOT / "services" / "stock_reconciliation_service.py",
    "almdina_erp.almdina_erp.services.reservation_service": RUNTIME_ROOT / "services" / "reservation_service.py",
    "almdina_erp.almdina_erp.services.material_reservation": RUNTIME_ROOT / "services" / "material_reservation.py",
    "almdina_erp.almdina_erp.services.remnant_service": RUNTIME_ROOT / "services" / "remnant_service.py",
    "almdina_erp.almdina_erp.services.remnant_execution": RUNTIME_ROOT / "services" / "remnant_execution.py",
    "almdina_erp.almdina_erp.services.remnant_planning": RUNTIME_ROOT / "services" / "remnant_planning.py",
    "almdina_erp.almdina_erp.infrastructure.stock_execution_gateway": RUNTIME_ROOT / "infrastructure" / "stock_execution_gateway.py",
    "almdina_erp.almdina_erp.infrastructure.remnant_execution_gateway": RUNTIME_ROOT / "infrastructure" / "remnant_execution_gateway.py",
    "almdina_erp.almdina_erp.infrastructure.frappe.inventory_repository": RUNTIME_ROOT / "infrastructure" / "frappe" / "inventory_repository.py",
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

    def test_retired_stock_group_has_no_external_runtime_consumers(self) -> None:
        target_paths = set(LEGACY_STOCK_MODULES.values())
        offenders: list[str] = []
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            if path in target_paths:
                continue
            source = path.read_text(encoding="utf-8")
            for module in LEGACY_STOCK_MODULES:
                if module in source:
                    offenders.append(f"{path.relative_to(ROOT)} -> {module}")
        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
