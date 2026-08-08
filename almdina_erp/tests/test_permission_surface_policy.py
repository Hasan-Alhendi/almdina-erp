from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.surface_access import (
    ALL_SURFACES,
    Surface,
    build_surface_access,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class TestPermissionSurfacePolicy(unittest.TestCase):
    def test_order_entry_dependencies_do_not_expose_master_data_admin(self) -> None:
        surfaces = build_surface_access(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.VIEW_CUSTOMERS,
                Capability.VIEW_EDGE_BANDING_TYPES,
            }
        )
        self.assertTrue(surfaces[Surface.ORDERS])
        self.assertFalse(surfaces[Surface.CUSTOMER_ADMIN])
        self.assertFalse(surfaces[Surface.EDGE_BANDING_TYPES])
        self.assertFalse(surfaces[Surface.FACTORY_MASTER_DATA])

    def test_workforce_and_permission_admin_surfaces_are_explicit(self) -> None:
        workforce = build_surface_access({Capability.VIEW_USERS})
        self.assertTrue(workforce[Surface.WORKFORCE])
        self.assertFalse(workforce[Surface.PERMISSIONS])
        self.assertFalse(workforce[Surface.ROLE_ADMIN])

        permissions = build_surface_access({Capability.MANAGE_PERMISSIONS})
        self.assertTrue(permissions[Surface.PERMISSIONS])
        self.assertTrue(permissions[Surface.ROLE_ADMIN])
        self.assertFalse(permissions[Surface.WORKFORCE])

    def test_operational_reports_do_not_expose_financial_order_analysis(self) -> None:
        surfaces = build_surface_access(
            {Capability.VIEW_ORDERS, Capability.VIEW_OPERATIONAL_REPORTS}
        )
        self.assertTrue(surfaces[Surface.REPORTS_WORKSPACE])
        self.assertTrue(surfaces[Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE])
        self.assertTrue(surfaces[Surface.REPORT_BOARD_USAGE])
        self.assertFalse(surfaces[Surface.REPORT_FACTORY_ORDER_ANALYSIS])

    def test_financial_report_surface_requires_financial_access(self) -> None:
        surfaces = build_surface_access(
            {
                Capability.VIEW_ORDERS,
                Capability.VIEW_COSTS,
                Capability.VIEW_OPERATIONAL_REPORTS,
                Capability.VIEW_FINANCIAL_REPORTS,
            }
        )
        self.assertTrue(surfaces[Surface.REPORT_FACTORY_ORDER_ANALYSIS])

    def test_reports_without_order_read_are_not_advertised(self) -> None:
        surfaces = build_surface_access({Capability.VIEW_OPERATIONAL_REPORTS})
        self.assertFalse(surfaces[Surface.REPORTS_WORKSPACE])
        self.assertFalse(surfaces[Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE])

    def test_production_incidents_have_independent_view_surface(self) -> None:
        denied = build_surface_access({Capability.RECORD_INCIDENT})
        allowed = build_surface_access({Capability.VIEW_PRODUCTION_INCIDENTS})
        self.assertFalse(denied[Surface.PRODUCTION_INCIDENTS])
        self.assertTrue(allowed[Surface.PRODUCTION_INCIDENTS])

    def test_administrator_gets_every_surface(self) -> None:
        surfaces = build_surface_access(set(), system_administrator=True)
        self.assertEqual(set(surfaces), set(ALL_SURFACES))
        self.assertTrue(all(surfaces.values()))


if __name__ == "__main__":
    unittest.main()
