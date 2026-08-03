from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.editability import (
    can_edit_order,
    can_recalculate_drawing_system_plan,
    is_draft_like,
    is_drawing_stage,
    is_locked_status,
)


class TestOrderEditabilityPolicy(unittest.TestCase):
    def test_draft_like_orders_are_editable_without_privileged_roles(self) -> None:
        for status in (None, "Draft", "Pending Review", "Rejected"):
            with self.subTest(status=status):
                self.assertTrue(is_draft_like(status))
                self.assertTrue(can_edit_order(status, roles=()))

    def test_approved_and_production_orders_are_immutable_for_every_role(self) -> None:
        for status in ("Approved", "At Drawing", "Cutting In Progress", "Ready for Delivery"):
            for role in ("Order Entry", "Production Manager", "System Manager", "Cutting Operator"):
                with self.subTest(status=status, role=role):
                    self.assertFalse(can_edit_order(status, roles={role}))

    def test_locked_orders_are_never_editable(self) -> None:
        for status in ("Delivered", "Cancelled"):
            with self.subTest(status=status):
                self.assertTrue(is_locked_status(status))
                self.assertFalse(can_edit_order(status, roles={"System Manager"}))

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

    def test_drawing_recalculation_requires_permission_stage_and_unapproved_plan(self) -> None:
        allowed = dict(
            has_recalculate_permission=True,
            approved_plan=None,
            production_path="Drawing",
            status="At Drawing",
            current_stage_type=None,
        )
        self.assertTrue(can_recalculate_drawing_system_plan(**allowed))

        blocked_cases = (
            {**allowed, "has_recalculate_permission": False},
            {**allowed, "approved_plan": "PLAN-0001"},
            {**allowed, "status": "At CNC", "current_stage_type": "CNC"},
        )
        for case in blocked_cases:
            with self.subTest(case=case):
                self.assertFalse(can_recalculate_drawing_system_plan(**case))

        self.assertTrue(
            can_recalculate_drawing_system_plan(
                **{
                    **allowed,
                    "production_path": "Custom Routed Production",
                    "status": "Production In Progress",
                    "current_stage_type": "Drawing",
                }
            )
        )

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
