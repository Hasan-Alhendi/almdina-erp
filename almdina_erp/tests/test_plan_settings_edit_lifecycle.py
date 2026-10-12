from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.services import plan_settings_edit_service as service


def _deterministic_throw(message, exc=None, *_args, **_kwargs):
    error_type = exc if isinstance(exc, type) else frappe.ValidationError
    raise error_type(message)


class TestPlanSettingsEditLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        bindings = (
            patch.object(service, "_", lambda message: message),
            patch.object(service.frappe, "throw", _deterministic_throw),
        )
        for binding in bindings:
            binding.start()
            self.addCleanup(binding.stop)

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
        service.assert_plan_settings_edit_lifecycle(order)

    def test_finished_route_without_active_stage_is_locked(self):
        order = self.order(
            status="Ready for Delivery",
            production_path="ROUTE-1",
            current_production_stage="",
        )

        with self.assertRaises(frappe.PermissionError):
            service.assert_plan_settings_edit_lifecycle(order)

    def test_preproduction_draft_remains_editable(self):
        service.assert_plan_settings_edit_lifecycle(self.order(status="Draft"))

    def test_preproduction_draft_remains_editable_with_approved_plan_and_planned_route(self):
        service.assert_plan_settings_edit_lifecycle(
            self.order(
                approved_plan="CP-0001",
                production_path="ROUTE-1",
            )
        )

    def test_approved_plan_is_locked_after_leaving_draft_and_drawing(self):
        with self.assertRaises(frappe.ValidationError):
            service.assert_plan_settings_edit_lifecycle(
                self.order(
                    status="At CNC",
                    approved_plan="CP-0001",
                )
            )

    def test_hard_document_locks_still_fail_closed(self):
        locked_orders = (
            self.order(docstatus=1),
            self.order(revision_state="Superseded"),
        )

        for order in locked_orders:
            with self.subTest(order=order):
                with self.assertRaises(frappe.ValidationError):
                    service.assert_plan_settings_edit_lifecycle(order)


if __name__ == "__main__":
    unittest.main()
