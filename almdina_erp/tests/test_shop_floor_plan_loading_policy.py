from __future__ import annotations

import unittest
from types import SimpleNamespace

from almdina_erp.almdina_erp.application.shop_floor.queries import _plan_snapshots


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
            can_view_plan=False,
        )

        self.assertEqual(repository.loads, [])
        self.assertEqual(result[0], {})
        self.assertEqual(result[1], {})
        self.assertEqual(result[2], {})
        self.assertFalse(result[3])

    def test_authorized_user_loads_system_and_custom_snapshots(self) -> None:
        repository = FakePlanRepository()
        order = SimpleNamespace(
            approved_plan=None,
            approved_plan_source="System",
        )

        result = _plan_snapshots(
            repository,
            order,
            can_view_plan=True,
        )

        self.assertEqual(repository.loads, ["System", "Custom"])
        self.assertTrue(result[0]["sheets"])
        self.assertTrue(result[1]["sheets"])
        self.assertTrue(result[3])


if __name__ == "__main__":
    unittest.main()
