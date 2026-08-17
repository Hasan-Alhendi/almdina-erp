from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.editability import (
    can_edit_order,
    can_recalculate_drawing_system_plan,
    is_before_cutting,
    is_draft_like,
    is_drawing_stage,
    is_locked_status,
)


class TestOrderEditabilityPolicy(unittest.TestCase):
    def test_only_draft_orders_are_editable(self) -> None:
        self.assertTrue(can_edit_order(None))
        self.assertTrue(can_edit_order("Draft"))
        self.assertTrue(can_edit_order("Draft", privileged=True))
        for status in (
            "Pending Review",
            "Rejected",
            "Approved",
            "At Drawing",
            "At Sharyoun",
            "At CNC",
            "Delivered",
            "Cancelled",
        ):
            with self.subTest(status=status):
                self.assertFalse(can_edit_order(status, roles=()))
                self.assertFalse(can_edit_order(status, privileged=True))
                self.assertFalse(can_edit_order(status, roles={"Order Entry"}))

    def test_draft_like_helper_still_covers_legacy_review_states(self) -> None:
        for status in (None, "Draft", "Pending Review", "Rejected"):
            with self.subTest(status=status):
                self.assertTrue(is_draft_like(status))

    def test_cutting_and_later_orders_are_not_before_cutting(self) -> None:
        for status in (
            "At Sharyoun",
            "At CNC",
            "At Sanding",
            "Ready for Delivery",
            "Delivered",
            "Cancelled",
            "Completed",
        ):
            with self.subTest(status=status):
                self.assertFalse(is_before_cutting(status))
                self.assertFalse(can_edit_order(status, privileged=True))

    def test_locked_orders_are_never_editable(self) -> None:
        for status in ("Delivered", "Cancelled"):
            with self.subTest(status=status):
                self.assertTrue(is_locked_status(status))
                self.assertFalse(can_edit_order(status, roles={"System Manager"}))
                self.assertFalse(can_edit_order(status, privileged=True))

    def test_drawing_stage_can_be_resolved_from_status_or_stage_type(self) -> None:
        self.assertTrue(
            is_drawing_stage(
                production_path="Drawing",
                status="At Drawing",
                current_stage_type=None,
            )
        )
        self.assertTrue(
            is_drawing_stage(
                production_path="Custom Routed Production",
                status="Production In Progress",
                current_stage_type="Drawing",
            )
        )
        self.assertFalse(
            is_drawing_stage(
                production_path="CNC",
                status="At CNC",
                current_stage_type="CNC",
            )
        )

    def test_drawing_recalculation_allows_preparing_replacement_for_approved_plan(self) -> None:
        allowed = dict(
            has_recalculate_permission=True,
            approved_plan=None,
            production_path="Drawing",
            status="At Drawing",
            current_stage_type=None,
        )
        self.assertTrue(can_recalculate_drawing_system_plan(**allowed))
        self.assertTrue(
            can_recalculate_drawing_system_plan(
                **{**allowed, "approved_plan": "PLAN-0001"}
            )
        )

        blocked_cases = (
            {**allowed, "has_recalculate_permission": False},
            {
                **allowed,
                "approved_plan": "PLAN-0001",
                "status": "At CNC",
                "current_stage_type": "CNC",
            },
            {
                **allowed,
                "approved_plan": "PLAN-0001",
                "status": "At Sanding",
                "current_stage_type": "Sanding",
            },
        )
        for case in blocked_cases:
            with self.subTest(case=case):
                self.assertFalse(can_recalculate_drawing_system_plan(**case))

    def test_domain_module_has_no_framework_dependency(self) -> None:
        domain_source = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "domain"
            / "orders"
            / "editability.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("import frappe", domain_source)
        self.assertNotIn("from frappe", domain_source)
        self.assertNotIn("frappe.db", domain_source)


if __name__ == "__main__":
    unittest.main()
