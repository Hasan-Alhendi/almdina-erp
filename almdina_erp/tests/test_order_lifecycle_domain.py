from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    ORDER_STATUSES,
    SHOP_FLOOR_ORDER_STATUSES,
    StageState,
    can_dispatch_from_status,
    can_mark_delivered,
    can_return_to_draft,
    can_revert_department,
    can_transition_stage,
    derive_order_status,
    is_order_dispatched,
    order_status_for_stage_type,
    resolve_shop_floor_stage_type,
    transition_stage,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = REPOSITORY_ROOT / "almdina_erp/almdina_erp"
DOMAIN_SOURCE = RUNTIME_ROOT / "domain/orders/lifecycle.py"
DOCTYPE_JSON = (
    RUNTIME_ROOT
    / "doctype/door_cutting_order/door_cutting_order.json"
)


class OrderLifecycleDomainTests(unittest.TestCase):
    def test_domain_has_no_framework_dependency(self) -> None:
        source = DOMAIN_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn("frappe.", source)

    def test_order_status_contract_matches_doctype(self) -> None:
        definition = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
        status_field = next(
            field for field in definition["fields"] if field.get("fieldname") == "status"
        )
        self.assertEqual(tuple(status_field["options"].splitlines()), ORDER_STATUSES)

    def test_runtime_has_no_fixed_production_route_catalog(self) -> None:
        forbidden = (
            "PRODUCTION" + "_PATHS",
            "production_path_" + "sequence(",
            "first_stage_" + "type(",
            "next_stage_" + "type(",
            "stage_" + "sequence(",
        )
        violations: list[str] = []
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    violations.append(f"{path.relative_to(RUNTIME_ROOT)}: {token}")
        self.assertEqual(violations, [])

    def test_custom_stage_codes_remain_valid_without_a_route_catalog(self) -> None:
        self.assertEqual(resolve_shop_floor_stage_type("PVC"), "PVC")
        self.assertEqual(resolve_shop_floor_stage_type("Laser Engraving"), "Laser Engraving")
        self.assertEqual(order_status_for_stage_type("PVC"), "Production In Progress")
        self.assertEqual(order_status_for_stage_type("Laser Engraving"), "Production In Progress")

    def test_stage_transition_matrix(self) -> None:
        expected = {
            ("Pending", "start"): "In Progress",
            ("In Progress", "pause"): "Paused",
            ("Paused", "resume"): "In Progress",
            ("In Progress", "finish"): "Completed",
            ("Paused", "finish"): "Completed",
            ("Completed", "cancel"): "Cancelled",
            ("Cancelled", "reopen"): "Pending",
        }
        for (current, event), target in expected.items():
            with self.subTest(current=current, event=event):
                self.assertTrue(can_transition_stage(current, event))
                self.assertEqual(transition_stage(current, event), target)

        invalid = (
            ("Paused", "start"),
            ("Pending", "pause"),
            ("In Progress", "resume"),
            ("Pending", "finish"),
            ("Completed", "start"),
        )
        for current, event in invalid:
            with self.subTest(current=current, event=event):
                self.assertFalse(can_transition_stage(current, event))
                with self.assertRaises(ValueError):
                    transition_stage(current, event)

    def test_order_transition_guards_preserve_existing_policy(self) -> None:
        for status in ("Draft", "Rejected", "Approved"):
            self.assertTrue(can_dispatch_from_status(status))
        for status in ("Pending Review", "At Drawing", "Delivered", "Cancelled"):
            self.assertFalse(can_dispatch_from_status(status))

        self.assertFalse(is_order_dispatched(production_path=None, current_stage=None))
        self.assertTrue(is_order_dispatched(production_path="Custom Route", current_stage=None))
        self.assertTrue(is_order_dispatched(production_path=None, current_stage="PST-1"))

        self.assertTrue(can_mark_delivered("Ready for Delivery"))
        self.assertFalse(can_mark_delivered("At Sanding"))

        for status in ("Pending Review", "Approved", "At CNC", "Ready for Delivery"):
            self.assertTrue(can_return_to_draft(status))
        for status in ("Draft", "Rejected", "Delivered", "Cancelled"):
            self.assertFalse(can_return_to_draft(status))

        self.assertTrue(can_revert_department("At CNC", production_path="Custom Route"))
        self.assertFalse(can_revert_department("Delivered", production_path="Custom Route"))
        self.assertFalse(can_revert_department("At CNC", production_path=None))

    def test_replacement_status_has_highest_priority(self) -> None:
        status = derive_order_status(
            current_status="Delivered",
            production_path="Custom Route",
            current_stage=StageState("PVC", "In Progress"),
            stages=(StageState("PVC", "In Progress"),),
            has_open_replacements=True,
        )
        self.assertEqual(status, "Replacement Required")

    def test_ready_and_delivered_statuses_are_preserved(self) -> None:
        for current in ("Ready for Delivery", "Delivered"):
            with self.subTest(current=current):
                status = derive_order_status(
                    current_status=current,
                    production_path="Custom Route",
                    current_stage=StageState("PVC", "Pending"),
                    stages=(StageState("PVC", "Pending"),),
                    has_open_replacements=False,
                )
                self.assertEqual(status, current)

    def test_current_stage_owns_dispatched_order_status(self) -> None:
        for stage_type, expected in SHOP_FLOOR_ORDER_STATUSES.items():
            with self.subTest(stage_type=stage_type):
                status = derive_order_status(
                    current_status="Approved",
                    production_path="Configured Route",
                    current_stage=StageState(stage_type, "Pending"),
                    stages=(),
                    has_open_replacements=False,
                )
                self.assertEqual(status, expected)

        custom = derive_order_status(
            current_status="Approved",
            production_path="Configured Route",
            current_stage=StageState("PVC", "Pending"),
            stages=(),
            has_open_replacements=False,
        )
        self.assertEqual(custom, "Production In Progress")

        preserved = derive_order_status(
            current_status="At CNC",
            production_path="Configured Route",
            current_stage=StageState("CNC", "Cancelled"),
            stages=(),
            has_open_replacements=False,
        )
        self.assertEqual(preserved, "At CNC")

    def test_status_is_derived_from_ordered_base_stages(self) -> None:
        cases = (
            ((StageState("Cutting", "Pending"),), "Cutting In Progress"),
            ((StageState("Edge Banding", "Paused"),), "Edge Banding In Progress"),
            ((StageState("Quality Check", "In Progress"),), "Quality Check"),
            ((StageState("Assembly", "Pending"),), "Production In Progress"),
            ((StageState("Cutting", "Completed"),), "Completed"),
            (
                (
                    StageState("Drawing", "Completed"),
                    StageState("CNC", "Completed"),
                    StageState("Sanding", "Completed"),
                ),
                "Ready for Delivery",
            ),
        )
        for stages, expected in cases:
            with self.subTest(expected=expected):
                status = derive_order_status(
                    current_status="Approved",
                    production_path=None,
                    current_stage=None,
                    stages=iter(stages),
                    has_open_replacements=False,
                )
                self.assertEqual(status, expected)

    def test_no_stages_preserves_current_status_or_defaults_to_draft(self) -> None:
        self.assertEqual(
            derive_order_status(
                current_status="On Hold",
                production_path=None,
                current_stage=None,
                stages=(),
                has_open_replacements=False,
            ),
            "On Hold",
        )
        self.assertEqual(
            derive_order_status(
                current_status=None,
                production_path=None,
                current_stage=None,
                stages=(),
                has_open_replacements=False,
            ),
            "Draft",
        )


if __name__ == "__main__":
    unittest.main()
