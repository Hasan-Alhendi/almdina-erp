from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.application.shop_floor import queries
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class FakeRepository:
    def __init__(self) -> None:
        self.user = "drawing@example.com"
        self.admin = False
        self.capabilities = set(queries.SHOP_FLOOR_DETAIL_CAPABILITIES)
        self.global_grants = set(self.capabilities)
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

    def current_user(self) -> str:
        return self.user

    def session_identity(self) -> dict[str, Any]:
        return {
            "user": self.user,
            "full_name": "Drawing Worker",
            "departments": ["رسم"],
            "roles": ["must-not-leak"],
        }

    def global_capabilities(self) -> frozenset[str]:
        return frozenset(self.global_grants)

    def is_admin(self) -> bool:
        return self.admin

    def capabilities_for_order(self, order: Any) -> frozenset[str]:
        return frozenset(self.capabilities)

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
        return getattr(self.order, "status", None)

    def list_revert_stages(self, order_name: str) -> list[Any]:
        return list(self.revert_rows)

    def get_users_for_stage(self, stage_type: str) -> list[dict[str, str]]:
        return [{"name": f"{stage_type.lower()}@example.com", "full_name": stage_type}]


class TestShopFloorQueryApplication(unittest.TestCase):
    def test_session_context_is_capability_driven_and_does_not_expose_roles(self) -> None:
        repository = FakeRepository()
        context = queries.get_shop_floor_context(repository)
        self.assertEqual(context["identity"]["user"], repository.user)
        self.assertEqual(context["identity"]["departments"], ["رسم"])
        self.assertNotIn("roles", context["identity"])
        self.assertTrue(context["navigation"]["shared_shell"])
        self.assertTrue(context["capabilities"][Capability.START_ASSIGNED_STAGE])

        repository.global_grants.clear()
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_shop_floor_context(repository)

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
                "board_description": "MDF أبيض 18 مم",
                "edge_color": "أبيض",
                "status": "At Drawing",
                "production_path": "Drawing",
                "current_department": "رسم",
                "department_status": "قيد العمل",
                "current_production_stage": "PST-CURRENT",
                "drawing_dxf_status": "Approved by Drawing",
                "revision": 2,
            }
        }

        rows = queries.get_my_inbox(repository)

        self.assertEqual([row["name"] for row in rows], ["PST-CURRENT"])
        self.assertEqual(rows[0]["can_handoff_to"], "CNC")
        self.assertEqual(rows[0]["department_label"], "رسم")
        self.assertEqual(rows[0]["edge_color"], "أبيض")
        self.assertEqual(rows[0]["board_description"], "MDF أبيض 18 مم")
        self.assertTrue(rows[0]["can_handoff_stage"])
        self.assertFalse(rows[0]["can_start_stage"])
        self.assertEqual(repository.last_inbox_args, (repository.user, False))

    def test_guest_ungranted_and_unassigned_order_are_rejected(self) -> None:
        repository = FakeRepository()
        repository.user = "Guest"
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_my_inbox(repository)

        repository.user = "worker@example.com"
        repository.global_grants.clear()
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_my_inbox(repository)

        repository.global_grants = {Capability.START_ASSIGNED_STAGE}
        repository.order = SimpleNamespace(name="DCO-1")
        repository.can_view = False
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_order_detail(repository, "DCO-1")

    def test_dispatch_options_require_capability_and_ready_order(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-1",
            status="Approved",
            production_path=None,
            current_production_stage=None,
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
            drawing_dxf_status="None",
        )

        result = queries.get_dispatch_options(repository, "DCO-1")
        self.assertEqual([row["value"] for row in result["paths"]], ["Sharyoun", "Drawing"])

        repository.capabilities.remove(Capability.DISPATCH_ORDER)
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_dispatch_options(repository, "DCO-1")

    def test_order_detail_uses_server_action_and_document_context(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-2",
            customer="Customer",
            status="At Drawing",
            production_path="Drawing",
            current_production_stage="PST-2",
            approved_plan=None,
            approved_plan_source="System",
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
            drawing_dxf_status="Approved by Drawing",
        )
        repository.order_stages = [
            {"name": "PST-2", "stage_type": "Drawing", "piece_label": None}
        ]
        repository.stage_summaries = {
            "PST-2": {
                "name": "PST-2",
                "status": "In Progress",
                "stage_type": "Drawing",
                "assigned_to": repository.user,
            }
        }
        repository.snapshots = {
            "System": {"sheets": [{"sheet_no": 1, "pieces": []}]},
            "Custom": {},
        }

        detail = queries.get_order_detail(repository, "DCO-2")
        actions = detail["stage_snapshot"]["production_actions"]

        self.assertEqual(detail["active_plan_source"], "System")
        self.assertEqual(detail["stage_snapshot"]["active_stage_type"], "Drawing")
        self.assertEqual(detail["stage_snapshot"]["active_stage_assigned_to"], repository.user)
        self.assertEqual(detail["stage_snapshot"]["can_handoff_to"], "CNC")
        self.assertTrue(detail["stage_snapshot"]["can_handoff_stage"])
        self.assertTrue(detail["stage_snapshot"]["can_reassign_worker"])
        self.assertTrue(actions[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"])
        self.assertTrue(actions[Capability.REASSIGN_WORKER]["allowed"])
        self.assertTrue(detail["can_recalculate_drawing_plan"])
        self.assertTrue(detail["document_capabilities"][Capability.VIEW_CUTTING_PLAN])
        self.assertTrue(detail["document_capabilities"][Capability.PRINT_CUTTING_PLAN])

        repository.capabilities.remove(Capability.RECALCULATE_PLAN)
        detail = queries.get_order_detail(repository, "DCO-2")
        self.assertFalse(detail["can_recalculate_drawing_plan"])

    def test_action_context_denies_another_workers_stage(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-2",
            customer="Customer",
            status="At CNC",
            production_path="Drawing",
            current_production_stage="PST-2",
            approved_plan="PLAN-1",
            approved_plan_source="System",
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
            drawing_dxf_status="Approved by Drawing",
        )
        repository.stage_summaries = {
            "PST-2": {
                "name": "PST-2",
                "status": "Pending",
                "stage_type": "CNC",
                "assigned_to": "other@example.com",
            }
        }

        detail = queries.get_order_detail(repository, "DCO-2")
        actions = detail["stage_snapshot"]["production_actions"]

        self.assertFalse(detail["stage_snapshot"]["can_start_stage"])
        self.assertEqual(
            actions[Capability.START_ASSIGNED_STAGE]["code"],
            "not_assigned",
        )
        self.assertTrue(detail["stage_snapshot"]["can_reassign_worker"])

    def test_revert_targets_are_unique_and_permission_protected(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-1",
            status="At CNC",
            production_path="Drawing",
            current_production_stage="PST-3",
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
            drawing_dxf_status="Approved by Drawing",
        )
        repository.revert_rows = [
            {"name": "PST-1", "stage_type": "Drawing", "status": "Completed", "sequence": 10, "assigned_to": "a@example.com", "piece_label": None},
            {"name": "PST-2", "stage_type": "Drawing", "status": "Completed", "sequence": 11, "assigned_to": "b@example.com", "piece_label": None},
            {"name": "PST-3", "stage_type": "CNC", "status": "Pending", "sequence": 20, "assigned_to": "c@example.com", "piece_label": None},
        ]

        targets = queries.get_revert_targets(repository, "DCO-1")
        self.assertEqual([target["stage_type"] for target in targets], ["Drawing", "CNC"])

        repository.capabilities.remove(Capability.REVERT_DEPARTMENT)
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_revert_targets(repository, "DCO-1")

        repository.capabilities.add(Capability.REVERT_DEPARTMENT)
        repository.order.status = "Delivered"
        with self.assertRaises(queries.ShopFloorQueryError):
            queries.get_revert_targets(repository, "DCO-1")


if __name__ == "__main__":
    unittest.main()
