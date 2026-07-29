from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.application.shop_floor import queries


class FakeRepository:
    def __init__(self) -> None:
        self.user = "drawing@example.com"
        self.admin = False
        self.inbox: list[Any] = []
        self.archive: list[Any] = []
        self.current: dict[str, str | None] = {}
        self.orders: dict[str, Any] = {}
        self.order: Any = None
        self.order_stages: list[Any] = []
        self.stage_summaries: dict[str, Any] = {}
        self.snapshots: dict[str | None, dict[str, Any]] = {}
        self.can_view = True
        self.dual_plans = True
        self.revert_rows: list[Any] = []
        self.status = "At Drawing"

    def current_user(self) -> str:
        return self.user

    def is_admin(self) -> bool:
        return self.admin

    def list_inbox_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        self.last_inbox_args = (user, is_admin)
        return list(self.inbox)

    def list_archive_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        return list(self.archive)

    def current_stage_names(self, order_names):
        return dict(self.current)

    def order_summaries(self, order_names):
        return dict(self.orders)

    def get_order(self, order_name: str) -> Any:
        return self.order

    def can_view_order(self, order: Any) -> bool:
        return self.can_view

    def list_order_stages(self, order_name: str) -> list[Any]:
        return list(self.order_stages)

    def get_stage_summary(self, stage_name: str) -> Any | None:
        return self.stage_summaries.get(stage_name)

    def load_plan_snapshot(self, order: Any, plan_source: str | None = None):
        return dict(self.snapshots.get(plan_source, {}))

    def user_can_view_dual_plans(self) -> bool:
        return self.dual_plans

    def get_order_status(self, order_name: str) -> str | None:
        return self.status

    def list_revert_stages(self, order_name: str) -> list[Any]:
        return list(self.revert_rows)

    def get_users_for_stage(self, stage_type: str) -> list[dict[str, str]]:
        return [{"name": f"{stage_type.lower()}@example.com", "full_name": stage_type}]


class TestShopFloorQueryApplication(unittest.TestCase):
    def test_inbox_filters_stale_rows_and_enriches_current_stage(self) -> None:
        repository = FakeRepository()
        repository.inbox = [
            {
                "name": "PST-OLD",
                "door_cutting_order": "DCO-1",
                "stage_type": "Drawing",
                "status": "Completed",
                "assigned_to": repository.user,
            },
            {
                "name": "PST-CURRENT",
                "door_cutting_order": "DCO-1",
                "stage_type": "Drawing",
                "status": "In Progress",
                "assigned_to": repository.user,
            },
        ]
        repository.current = {"DCO-1": "PST-CURRENT"}
        repository.orders = {
            "DCO-1": {
                "customer": "Customer",
                "status": "At Drawing",
                "production_path": "Drawing",
                "current_department": "رسم",
                "department_status": "قيد العمل",
                "revision": 2,
            }
        }

        rows = queries.get_my_inbox(repository)

        self.assertEqual([row["name"] for row in rows], ["PST-CURRENT"])
        self.assertEqual(rows[0]["can_handoff_to"], "CNC")
        self.assertEqual(rows[0]["department_label"], "رسم")
        self.assertEqual(repository.last_inbox_args, (repository.user, False))

    def test_guest_and_unassigned_order_are_rejected(self) -> None:
        repository = FakeRepository()
        repository.user = "Guest"
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_my_inbox(repository)

        repository.user = "worker@example.com"
        repository.order = SimpleNamespace(name="DCO-1")
        repository.can_view = False
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_order_detail(repository, "DCO-1")

    def test_order_detail_selects_active_plan_and_stage_actions(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-2",
            customer="Customer",
            status="At Drawing",
            production_path="Drawing",
            current_production_stage="PST-2",
            approved_plan=None,
            approved_plan_source="System",
        )
        repository.order_stages = [
            {"name": "PST-2", "stage_type": "Drawing", "piece_label": None}
        ]
        repository.stage_summaries = {
            "PST-2": {
                "name": "PST-2",
                "status": "In Progress",
                "stage_type": "Drawing",
            }
        }
        repository.snapshots = {
            "System": {"sheets": [{"sheet_no": 1, "pieces": []}]},
            "Custom": {},
        }

        detail = queries.get_order_detail(repository, "DCO-2")

        self.assertEqual(detail["active_plan_source"], "System")
        self.assertEqual(detail["stage_snapshot"]["active_stage_type"], "Drawing")
        self.assertEqual(detail["stage_snapshot"]["can_handoff_to"], "CNC")
        self.assertTrue(detail["stage_snapshot"]["can_handoff_stage"])
        self.assertTrue(detail["can_recalculate_drawing_plan"])

    def test_revert_targets_are_unique_and_delivered_orders_return_none(self) -> None:
        repository = FakeRepository()
        repository.revert_rows = [
            {
                "name": "PST-1",
                "stage_type": "Drawing",
                "status": "Completed",
                "sequence": 10,
                "assigned_to": "a@example.com",
                "piece_label": None,
            },
            {
                "name": "PST-2",
                "stage_type": "Drawing",
                "status": "Completed",
                "sequence": 11,
                "assigned_to": "b@example.com",
                "piece_label": None,
            },
            {
                "name": "PST-3",
                "stage_type": "CNC",
                "status": "Pending",
                "sequence": 20,
                "assigned_to": "c@example.com",
                "piece_label": None,
            },
        ]

        targets = queries.get_revert_targets(repository, "DCO-1")
        self.assertEqual([target["stage_type"] for target in targets], ["Drawing", "CNC"])

        repository.status = "Delivered"
        self.assertEqual(queries.get_revert_targets(repository, "DCO-1"), [])


if __name__ == "__main__":
    unittest.main()
