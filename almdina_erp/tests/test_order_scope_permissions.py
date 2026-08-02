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

    def test_cost_and_supervisor_grants_open_broad_order_scope(self) -> None:
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
                    self.assertFalse(
                        permissions._requires_assigned_scope(
                            "supervisor@example.com"
                        )
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


if __name__ == "__main__":
    unittest.main()
