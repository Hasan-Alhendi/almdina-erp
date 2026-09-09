from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    ORDER_STATUSES,
    PRODUCTION_ORDER_STATUS,
    StageState,
    can_dispatch_from_status,
    can_mark_delivered,
    can_return_to_draft,
    can_revert_department,
    can_transition_stage,
    derive_order_status,
    is_order_dispatched,
    next_stage_type,
    production_path_sequence,
    stage_sequence,
    transition_stage,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_SOURCE = REPOSITORY_ROOT / "almdina_erp/almdina_erp/domain/orders/lifecycle.py"
DOCTYPE_JSON = REPOSITORY_ROOT / "almdina_erp/almdina_erp/doctype/door_cutting_order/door_cutting_order.json"


class OrderLifecycleDomainTests(unittest.TestCase):
    def test_domain_has_no_framework_dependency(self) -> None:
        source = DOMAIN_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn("frappe.", source)

    def test_order_status_contract_matches_doctype(self) -> None:
        definition = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
        status_field = next(field for field in definition["fields"] if field.get("fieldname") == "status")
        self.assertEqual(tuple(status_field["options"].splitlines()), ORDER_STATUSES)

    def test_fixed_production_path_registry_is_retired(self) -> None:
        for call in (
            lambda: production_path_sequence("Drawing"),
            lambda: next_stage_type("Drawing", "Drawing"),
            lambda: stage_sequence("Drawing", "Drawing"),
        ):
            with self.assertRaisesRegex(ValueError, "Fixed production paths are retired"):
                call()

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

    def test_order_transition_guards_preserve_capability_policy(self) -> None:
        for status in ("Draft", "Rejected", "Pending Review", "Approved"):
            self.assertTrue(can_dispatch_from_status(status))
        for status in (PRODUCTION_ORDER_STATUS, "Delivered", "Cancelled"):
            self.assertFalse(can_dispatch_from_status(status))
        self.assertFalse(is_order_dispatched(production_path=None, current_stage=None))
        self.assertTrue(is_order_dispatched(production_path="Custom Route", current_stage=None))
        self.assertTrue(is_order_dispatched(production_path=None, current_stage="PST-1"))
        self.assertTrue(can_mark_delivered("Ready for Delivery"))
        self.assertFalse(can_mark_delivered(PRODUCTION_ORDER_STATUS))
        for status in ("Approved", PRODUCTION_ORDER_STATUS, "Ready for Delivery", "Delivered"):
            self.assertTrue(can_return_to_draft(status))
        self.assertTrue(can_revert_department(PRODUCTION_ORDER_STATUS, production_path="Custom Route"))

    def test_replacement_status_has_highest_priority(self) -> None:
        status = derive_order_status(
            current_status="Delivered",
            production_path="Custom Route",
            current_stage=StageState("ANY_STAGE", "In Progress"),
            stages=(StageState("ANY_STAGE", "In Progress"),),
            has_open_replacements=True,
        )
        self.assertEqual(status, "Replacement Required")

    def test_ready_delivered_and_cancelled_are_preserved(self) -> None:
        for current in ("Ready for Delivery", "Delivered", "Cancelled"):
            with self.subTest(current=current):
                status = derive_order_status(
                    current_status=current,
                    production_path="Custom Route",
                    current_stage=StageState("ANY_STAGE", "Pending"),
                    stages=(StageState("ANY_STAGE", "Pending"),),
                    has_open_replacements=False,
                )
                self.assertEqual(status, current)

    def test_current_physical_stage_never_becomes_order_status(self) -> None:
        for stage_type in ("CNC", "Drawing", "NEW_CUSTOM_STAGE", "مرحلة خاصة"):
            with self.subTest(stage_type=stage_type):
                status = derive_order_status(
                    current_status="Approved",
                    production_path="Custom Route",
                    current_stage=StageState(stage_type, "Pending"),
                    stages=(),
                    has_open_replacements=False,
                )
                self.assertEqual(status, PRODUCTION_ORDER_STATUS)

    def test_base_stage_derivation_is_route_neutral(self) -> None:
        for stage_type in ("Cutting", "Edge Banding", "Quality Check", "Anything"):
            status = derive_order_status(
                current_status="Approved",
                production_path=None,
                current_stage=None,
                stages=(StageState(stage_type, "In Progress"),),
                has_open_replacements=False,
            )
            self.assertEqual(status, PRODUCTION_ORDER_STATUS)
        self.assertEqual(
            derive_order_status(
                current_status="Approved",
                production_path=None,
                current_stage=None,
                stages=(StageState("Anything", "Completed"),),
                has_open_replacements=False,
            ),
            "Completed",
        )
        self.assertEqual(
            derive_order_status(
                current_status=PRODUCTION_ORDER_STATUS,
                production_path="Custom Route",
                current_stage=None,
                stages=(StageState("Anything", "Completed"),),
                has_open_replacements=False,
            ),
            "Ready for Delivery",
        )

    def test_no_stages_preserves_current_status_or_defaults_to_draft(self) -> None:
        self.assertEqual(
            derive_order_status(current_status="On Hold", production_path=None, current_stage=None, stages=(), has_open_replacements=False),
            "On Hold",
        )
        self.assertEqual(
            derive_order_status(current_status=None, production_path=None, current_stage=None, stages=(), has_open_replacements=False),
            "Draft",
        )


if __name__ == "__main__":
    unittest.main()
