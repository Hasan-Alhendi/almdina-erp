from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.navigation_context import (
    WORKSPACE_CONTROL_CENTER,
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.surface_access import (
    ALL_SURFACES,
    Surface,
    build_surface_access,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestPermissionSurfacePolicy(unittest.TestCase):
    def test_order_entry_lookup_support_does_not_expose_master_data_admin(self) -> None:
        surfaces = build_surface_access(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
            }
        )
        self.assertTrue(surfaces[Surface.ORDERS])
        self.assertFalse(surfaces[Surface.CUSTOMER_ADMIN])
        self.assertFalse(surfaces[Surface.EDGE_BANDING_TYPES])
        self.assertFalse(surfaces[Surface.FACTORY_MASTER_DATA])

    def test_explicit_edge_view_is_visible_even_for_order_entry_role(self) -> None:
        surfaces = build_surface_access(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.EDIT_ORDER,
                Capability.VIEW_EDGE_BANDING_TYPES,
            }
        )
        self.assertTrue(surfaces[Surface.ORDERS])
        self.assertTrue(surfaces[Surface.EDGE_BANDING_TYPES])
        self.assertFalse(surfaces[Surface.FACTORY_MASTER_DATA])
        self.assertFalse(surfaces[Surface.CUSTOMER_ADMIN])

    def test_routing_console_requires_routing_view(self) -> None:
        surfaces = build_surface_access({Capability.VIEW_PRODUCTION_ROUTINGS})
        self.assertTrue(surfaces[Surface.FACTORY_MASTER_DATA])
        self.assertTrue(surfaces[Surface.PRODUCTION_ROUTINGS])

    def test_explicit_customer_view_is_visible_even_for_order_entry_role(self) -> None:
        surfaces = build_surface_access(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.VIEW_CUSTOMERS,
            }
        )
        self.assertTrue(surfaces[Surface.CUSTOMER_ADMIN])
        self.assertFalse(surfaces[Surface.EDGE_BANDING_TYPES])

    def test_cutting_plan_approval_does_not_expose_drawing_or_control_center(self) -> None:
        navigation = build_navigation_context(
            {
                Capability.VIEW_ORDERS,
                Capability.VIEW_CUTTING_PLAN,
                Capability.APPROVE_DXF,
            }
        )
        self.assertTrue(navigation["sections"]["planning"])
        self.assertFalse(navigation["sections"]["drawing"])
        self.assertFalse(navigation["sections"]["quality"])
        self.assertFalse(navigation["sections"]["costing"])
        self.assertNotIn(WORKSPACE_CONTROL_CENTER, navigation["workspaces"])

    def test_control_center_pages_follow_their_exact_capabilities(self) -> None:
        review = build_surface_access({Capability.REJECT_ORDER})
        self.assertNotIn("approval_queue", review)
        self.assertFalse(review[Surface.PLAN_ARCHIVE])

        archive = build_surface_access({Capability.ARCHIVE_APPROVED_PLAN})
        self.assertNotIn("approval_queue", archive)
        self.assertTrue(archive[Surface.PLAN_ARCHIVE])

    def test_workforce_and_permission_admin_surfaces_are_explicit(self) -> None:
        workforce = build_surface_access({Capability.VIEW_USERS})
        self.assertTrue(workforce[Surface.WORKFORCE])
        self.assertFalse(workforce[Surface.PERMISSIONS])
        self.assertFalse(workforce[Surface.ROLE_ADMIN])

        permissions = build_surface_access({Capability.MANAGE_PERMISSIONS})
        self.assertTrue(permissions[Surface.PERMISSIONS])
        self.assertTrue(permissions[Surface.ROLE_ADMIN])
        self.assertFalse(permissions[Surface.WORKFORCE])

    def test_cost_view_does_not_add_a_report_surface(self) -> None:
        surfaces = build_surface_access(
            {Capability.VIEW_ORDERS, Capability.VIEW_COSTS}
        )
        self.assertNotIn("reports_workspace", surfaces)
        self.assertNotIn("report_factory_order_analysis", surfaces)
        self.assertTrue(surfaces[Surface.ORDERS])

    def test_administrator_gets_every_surface(self) -> None:
        surfaces = build_surface_access(set(), system_administrator=True)
        self.assertEqual(set(surfaces), set(ALL_SURFACES))
        self.assertTrue(all(surfaces.values()))


if __name__ == "__main__":
    unittest.main()
