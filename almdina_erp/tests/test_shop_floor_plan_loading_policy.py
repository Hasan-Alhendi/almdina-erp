from __future__ import annotations

import unittest
from types import SimpleNamespace

from almdina_erp.almdina_erp.application.shop_floor.queries import _plan_snapshots
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class FakePlanRepository:
    def __init__(self) -> None:
        self.loads: list[str | None] = []

    def load_plan_snapshot(self, order, plan_source=None):
        self.loads.append(plan_source)
        return {"sheets": [{"source": plan_source or "Approved"}]}

    def user_can_view_dual_plans(self) -> bool:
        return True


class TestShopFloorPlanLoadingPolicy(unittest.TestCase):
    def test_no_plan_snapshot_is_read_without_view_permission(self) -> None:
        repository = FakePlanRepository()
        order = SimpleNamespace(
            approved_plan="PLAN-1",
            approved_plan_source="Custom",
        )

        result = _plan_snapshots(
            repository,
            order,
            document_capabilities=frozenset(),
        )

        self.assertEqual(repository.loads, [])
        self.assertEqual(result["system_snapshot"], {})
        self.assertEqual(result["custom_snapshot"], {})
        self.assertEqual(result["approved_snapshot"], {})
        self.assertEqual(result["visible_plan_tabs"], [])
        self.assertFalse(result["show_dual_tabs"])

    def test_authorized_user_loads_system_custom_and_approved_snapshots(self) -> None:
        repository = FakePlanRepository()
        order = SimpleNamespace(
            approved_plan=None,
            approved_plan_source="System",
        )

        result = _plan_snapshots(
            repository,
            order,
            document_capabilities=frozenset(
                {
                    Capability.VIEW_CUTTING_PLAN,
                    Capability.VIEW_SYSTEM_CUTTING_PLAN,
                    Capability.VIEW_UPLOADED_CUTTING_PLAN,
                    Capability.VIEW_APPROVED_CUTTING_PLAN,
                }
            ),
        )

        self.assertEqual(repository.loads, ["System", "Custom", None])
        self.assertTrue(result["system_snapshot"]["sheets"])
        self.assertTrue(result["custom_snapshot"]["sheets"])
        self.assertTrue(result["approved_snapshot"]["sheets"])
        self.assertEqual(
            result["visible_plan_tabs"],
            ["System", "Custom", "Approved"],
        )
        self.assertTrue(result["show_dual_tabs"])

    def test_only_approved_tab_capability_loads_approved_snapshot(self) -> None:
        repository = FakePlanRepository()
        order = SimpleNamespace(
            approved_plan="PLAN-1",
            approved_plan_source="System",
        )

        result = _plan_snapshots(
            repository,
            order,
            document_capabilities=frozenset(
                {
                    Capability.VIEW_CUTTING_PLAN,
                    Capability.VIEW_APPROVED_CUTTING_PLAN,
                }
            ),
        )

        self.assertEqual(repository.loads, [None])
        self.assertEqual(result["visible_plan_tabs"], ["Approved"])
        self.assertEqual(result["active_plan_source"], "Approved")
        self.assertFalse(result["show_dual_tabs"])


if __name__ == "__main__":
    unittest.main()
