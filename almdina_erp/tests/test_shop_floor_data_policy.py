from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.presentation.shop_floor.data_policy import (
    sanitize_shop_floor_detail,
    sanitize_shop_floor_summary,
)


class TestShopFloorDataPolicy(unittest.TestCase):
    @staticmethod
    def payload() -> dict[str, object]:
        return {
            "name": "DCO-TEST",
            "approved_plan": "PLAN-1",
            "cutting_plan_html": "<div>plan</div>",
            "system_plan_json": '{"sheets":[]}',
            "production_dxf": "/private/files/order.dxf",
            "drawing_dxf_status": "Approved by Drawing",
        }

    def test_plan_permission_does_not_grant_dxf_data(self) -> None:
        sanitized = sanitize_shop_floor_detail(
            self.payload(),
            {Capability.VIEW_CUTTING_PLAN: True},
        )

        self.assertEqual(sanitized["approved_plan"], "PLAN-1")
        self.assertIn("cutting_plan_html", sanitized)
        self.assertNotIn("production_dxf", sanitized)
        self.assertNotIn("drawing_dxf_status", sanitized)

    def test_dxf_permission_does_not_grant_cutting_plan(self) -> None:
        sanitized = sanitize_shop_floor_detail(
            self.payload(),
            {Capability.EXPORT_DXF: True},
        )

        self.assertEqual(sanitized["production_dxf"], "/private/files/order.dxf")
        self.assertIn("drawing_dxf_status", sanitized)
        self.assertNotIn("approved_plan", sanitized)
        self.assertNotIn("cutting_plan_html", sanitized)
        self.assertNotIn("system_plan_json", sanitized)

    def test_summary_removes_protected_fields_without_grants(self) -> None:
        rows = sanitize_shop_floor_summary([self.payload()], frozenset())

        self.assertEqual(rows[0]["name"], "DCO-TEST")
        self.assertNotIn("approved_plan", rows[0])
        self.assertNotIn("production_dxf", rows[0])
        self.assertNotIn("drawing_dxf_status", rows[0])

    def test_summary_keeps_each_boundary_only_for_its_capability(self) -> None:
        plan_rows = sanitize_shop_floor_summary(
            [self.payload()],
            {Capability.VIEW_CUTTING_PLAN},
        )
        dxf_rows = sanitize_shop_floor_summary(
            [self.payload()],
            {Capability.VIEW_DRAWING_WORKSPACE},
        )

        self.assertIn("approved_plan", plan_rows[0])
        self.assertNotIn("production_dxf", plan_rows[0])
        self.assertNotIn("approved_plan", dxf_rows[0])
        self.assertIn("production_dxf", dxf_rows[0])


if __name__ == "__main__":
    unittest.main()
