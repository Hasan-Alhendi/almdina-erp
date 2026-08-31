from __future__ import annotations

import unittest
from unittest.mock import patch

from almdina_erp import permissions
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestOrderScopePermissions(unittest.TestCase):
    @staticmethod
    def capability_checker(granted: set[str]):
        return lambda capability, user=None: capability in granted

    def test_operator_with_customer_document_grants_stays_assigned_only(self) -> None:
        granted = {
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
            Capability.PRINT_MEASUREMENTS,
            Capability.PRINT_CUSTOMER_INVOICE,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            self.assertTrue(
                permissions._requires_assigned_scope("worker@example.com")
            )

    def test_adjacent_and_supervisor_grants_do_not_open_broad_scope(self) -> None:
        for capability in (
            Capability.VIEW_COSTS,
            Capability.EDIT_COST_SETTINGS,
            Capability.REASSIGN_WORKER,
            Capability.VIEW_OPERATIONAL_REPORTS,
        ):
            with self.subTest(capability=capability):
                granted = {
                    Capability.START_ASSIGNED_STAGE,
                    capability,
                }
                with patch.object(
                    permissions,
                    "doctype_has_capability",
                    side_effect=self.capability_checker(granted),
                ):
                    self.assertTrue(
                        permissions._requires_assigned_scope(
                            "supervisor@example.com"
                        )
                    )

    def test_explicit_global_order_grant_opens_broad_scope(self) -> None:
        granted = {
            Capability.VIEW_ORDERS,
            Capability.START_ASSIGNED_STAGE,
            Capability.REASSIGN_WORKER,
            Capability.VIEW_ALL_ORDERS,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            self.assertFalse(
                permissions._requires_assigned_scope("manager@example.com")
            )

    def test_master_data_and_permission_admin_do_not_expand_operator_scope(self) -> None:
        granted = {
            Capability.START_ASSIGNED_STAGE,
            Capability.VIEW_EDGE_BANDING_TYPES,
            Capability.MANAGE_PERMISSIONS,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            self.assertTrue(
                permissions._requires_assigned_scope("worker@example.com")
            )

    def test_worker_visible_orders_exclude_completed_without_history(self) -> None:
        granted = {Capability.START_ASSIGNED_STAGE, Capability.VIEW_ORDERS}
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            with patch.object(
                permissions,
                "_worker_operational_roles",
                return_value=("عامل رسم",),
            ):
                subquery = permissions._worker_visible_orders_subquery(
                    "worker@example.com"
                )
        self.assertNotIn("union", subquery.lower())
        self.assertIn("current_production_stage", subquery)
        self.assertNotIn("status = 'Completed'", subquery)
        self.assertIn("Draft", subquery)
        self.assertIn("Pending Review", subquery)
        self.assertIn("عامل رسم", subquery)

    def test_worker_visible_orders_include_completed_with_history(self) -> None:
        granted = {
            Capability.START_ASSIGNED_STAGE,
            Capability.VIEW_ORDERS,
            Capability.VIEW_SHOP_FLOOR_HISTORY,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            with patch.object(
                permissions,
                "_worker_operational_roles",
                return_value=("عامل رسم",),
            ):
                subquery = permissions._worker_visible_orders_subquery(
                    "worker@example.com"
                )
        self.assertIn("union", subquery.lower())
        self.assertIn("current_production_stage", subquery)
        self.assertIn("status = 'Completed'", subquery)

    def test_order_editing_grant_does_not_open_scope_for_floor_workers(self) -> None:
        # The drawing role carries edit_order so it can save plan settings. That
        # must not turn the worker into a whole-floor reader.
        granted = {
            Capability.VIEW_ORDERS,
            Capability.EDIT_ORDER,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
            Capability.RECALCULATE_PLAN,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            self.assertTrue(
                permissions._requires_assigned_scope("drawing@example.com")
            )

    def test_order_authoring_without_stage_work_keeps_broad_scope(self) -> None:
        granted = {
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.SUBMIT_ORDER,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            self.assertFalse(
                permissions._requires_assigned_scope("entry@example.com")
            )

    def test_drawing_planner_capabilities_still_require_assigned_scope(self) -> None:
        granted = {
            Capability.VIEW_ORDERS,
            Capability.RECALCULATE_PLAN,
            Capability.EDIT_OPTIMIZER_SETTINGS,
            Capability.VIEW_DRAWING_WORKSPACE,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            self.assertTrue(
                permissions._requires_assigned_scope("drawing@example.com")
            )

    def test_worker_cannot_open_completed_order_without_history(self) -> None:
        granted = {Capability.START_ASSIGNED_STAGE, Capability.VIEW_ORDERS}
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            with patch.object(
                permissions,
                "_worker_operational_roles",
                return_value=("عامل رسم",),
            ):
                delivered_order = {
                    "status": "Delivered",
                    "current_production_stage": None,
                }
                with patch.object(
                    permissions.frappe.db,
                    "exists",
                    return_value=True,
                ):
                    with patch.object(
                        permissions.frappe.db,
                        "get_value",
                        return_value=delivered_order,
                    ):
                        self.assertFalse(
                            permissions.worker_can_view_order(
                                "worker@example.com",
                                "DCO-DONE",
                            )
                        )

    def test_worker_can_open_completed_order_with_history(self) -> None:
        granted = {
            Capability.START_ASSIGNED_STAGE,
            Capability.VIEW_ORDERS,
            Capability.VIEW_SHOP_FLOOR_HISTORY,
        }
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            with patch.object(
                permissions,
                "_worker_operational_roles",
                return_value=("عامل رسم",),
            ):
                with patch.object(
                    permissions.frappe.db,
                    "exists",
                    return_value=True,
                ):
                    with patch.object(
                        permissions.frappe.db,
                        "get_value",
                        return_value={
                            "status": "Delivered",
                            "current_production_stage": None,
                        },
                    ):
                        self.assertTrue(
                            permissions.worker_can_view_order(
                                "worker@example.com",
                                "DCO-DONE",
                            )
                        )

    def test_worker_can_open_current_assignment_without_history(self) -> None:
        granted = {Capability.START_ASSIGNED_STAGE, Capability.VIEW_ORDERS}
        with patch.object(
            permissions,
            "doctype_has_capability",
            side_effect=self.capability_checker(granted),
        ):
            with patch.object(
                permissions,
                "_worker_operational_roles",
                return_value=("عامل رسم",),
            ):
                with patch.object(
                    permissions.frappe.db,
                    "exists",
                    return_value=False,
                ):
                    with patch.object(
                        permissions.frappe.db,
                        "get_value",
                        side_effect=[
                            {
                                "status": "At Drawing",
                                "current_production_stage": "PST-DRAW",
                            },
                            {
                                "assigned_to": "worker@example.com",
                                "operational_role": "عامل رسم",
                                "stage_type": "Drawing",
                            },
                        ],
                    ):
                        self.assertTrue(
                            permissions.worker_can_view_order(
                                "worker@example.com",
                                "DCO-MINE",
                            )
                        )

                    with patch.object(
                        permissions.frappe.db,
                        "get_value",
                        side_effect=[
                            {
                                "status": "At CNC",
                                "current_production_stage": "PST-CNC",
                            },
                            {
                                "assigned_to": "worker@example.com",
                                "operational_role": "عامل CNC",
                                "stage_type": "CNC",
                            },
                        ],
                    ):
                        self.assertFalse(
                            permissions.worker_can_view_order(
                                "worker@example.com",
                                "DCO-OTHER",
                            )
                        )

                    with patch.object(
                        permissions.frappe.db,
                        "get_value",
                        return_value={
                            "status": "Draft",
                            "current_production_stage": None,
                        },
                    ):
                        self.assertFalse(
                            permissions.worker_can_view_order(
                                "worker@example.com",
                                "DCO-DRAFT",
                            )
                        )


if __name__ == "__main__":
    unittest.main()
