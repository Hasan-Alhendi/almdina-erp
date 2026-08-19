from __future__ import annotations

from types import SimpleNamespace
import unittest

import frappe

from almdina_erp.almdina_erp.services.plan_settings_edit_service import (
    assert_plan_settings_edit_lifecycle,
)


class TestPlanSettingsEditLifecycle(unittest.TestCase):
    @staticmethod
    def order(**overrides):
        values = {
            "docstatus": 0,
            "approved_plan": "",
            "revision_state": "Current",
            "current_production_stage": "",
            "production_path": "",
            "status": "Draft",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_active_production_stage_does_not_require_worker_stage_role(self):
        order = self.order(
            status="In Production",
            production_path="ROUTE-1",
            current_production_stage="STAGE-1",
        )

        # The caller already passed the focused EDIT_OPTIMIZER_SETTINGS capability
        # check. Lifecycle validation must not add a second actor-role gate.
        assert_plan_settings_edit_lifecycle(order)

    def test_finished_route_without_active_stage_is_locked(self):
        order = self.order(
            status="Ready for Delivery",
            production_path="ROUTE-1",
            current_production_stage="",
        )

        with self.assertRaises(frappe.PermissionError):
            assert_plan_settings_edit_lifecycle(order)

    def test_preproduction_draft_remains_editable(self):
        assert_plan_settings_edit_lifecycle(self.order(status="Draft"))

    def test_hard_document_locks_still_fail_closed(self):
        locked_orders = (
            self.order(docstatus=1),
            self.order(approved_plan="CP-0001"),
            self.order(revision_state="Superseded"),
        )

        for order in locked_orders:
            with self.subTest(order=order):
                with self.assertRaises(frappe.ValidationError):
                    assert_plan_settings_edit_lifecycle(order)


if __name__ == "__main__":
    unittest.main()
