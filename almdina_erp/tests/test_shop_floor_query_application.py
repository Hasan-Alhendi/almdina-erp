from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.application.shop_floor import queries
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
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
        self.routes = {
            "Sharyoun": ProductionRoute(
                "Sharyoun",
                "شريون",
                (
                    RoutingStage(10, "Sharyoun", "شريون", "عامل شريون"),
                    RoutingStage(20, "Sanding", "تقشيط", "عامل تقشيط"),
                ),
            ),
            "Drawing": ProductionRoute(
                "Drawing",
                "رسم وCNC",
                (
                    RoutingStage(10, "Drawing", "رسم", "عامل رسم", True),
                    RoutingStage(20, "CNC", "CNC", "عامل CNC"),
                    RoutingStage(30, "Sanding", "تقشيط", "عامل تقشيط"),
                ),
            ),
        }

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

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]:
        return tuple(
            getattr(
                self,
                "roles",
                (
                    "عامل شريون",
                    "عامل رسم",
                    "عامل CNC",
                    "عامل تقشيط",
                    "مصمم مخصص",
                ),
            )
        )

    def is_admin(self) -> bool:
        return self.admin

    def capabilities_for_order(self, order: Any) -> frozenset[str]:
        return frozenset(self.capabilities)

    def list_active_routes(self) -> list[ProductionRoute]:
        return list(self.routes.values())

    def get_production_route(self, route_name: str) -> ProductionRoute:
        return self.routes[route_name]

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

    def get_users_for_role(self, role: str) -> list[dict[str, str]]:
        return [{"name": f"{role.lower()}@example.com", "full_name": role}]

    def default_production_route(self) -> str | None:
        return "Sharyoun"


class TestShopFloorQueryApplication(unittest.TestCase):
    def test_session_context_is_capability_driven_and_does_not_expose_roles(self) -> None:
        repository = FakeRepository()
        context = queries.get_shop_floor_context(repository)
        self.assertEqual(context["identity"]["user"], repository.user)
        self.assertEqual(context["identity"]["departments"], ["رسم"])
        self.assertNotIn("roles", context["identity"])
        self.assertTrue(context["navigation"]["shared_shell"])
        self.assertTrue(context["capabilities"][Capability.START_ASSIGNED_STAGE])
        self.assertEqual(
            [route["name"] for route in context["production_routes"]],
            ["Sharyoun", "Drawing"],
        )
        self.assertEqual(
            [stage["stage_type"] for stage in context["production_routes"][1]["stages"]],
            ["Drawing", "CNC", "Sanding"],
        )
        self.assertNotIn(
            "operational_role",
            context["production_routes"][1]["stages"][0],
        )

        repository.global_grants.clear()
        with self.assertRaisesRegex(queries.ShopFloorPermissionDenied, "صلاحية الدخول"):
            queries.get_shop_floor_context(repository)

    def test_inbox_hides_stale_rows_and_explains_planning_handoff_gate(self) -> None:
        repository = FakeRepository()
        repository.inbox = [
            {
                "name": "PST-OLD",
                "door_cutting_order": "DCO-1",
                "stage_type": "Drawing",
                "status": "Completed",
                "assigned_to": repository.user,
                "operational_role": "عامل رسم",
            },
            {
                "name": "PST-CURRENT",
                "door_cutting_order": "DCO-1",
                "stage_type": "Drawing",
                "status": "In Progress",
                "assigned_to": repository.user,
                "operational_role": "عامل رسم",
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
                "approved_plan": None,
                "plan_needs_recalculation": 0,
                "revision": 2,
            }
        }

        rows = queries.get_my_inbox(repository)

        self.assertEqual([row["name"] for row in rows], ["PST-CURRENT"])
        self.assertEqual(rows[0]["can_handoff_to"], "CNC")
        self.assertEqual(rows[0]["department_label"], "رسم")
        self.assertFalse(rows[0]["can_handoff_stage"])
        self.assertEqual(rows[0]["handoff_block_code"], "plan_not_approved")
        self.assertIn("اعتمد خطة القص", rows[0]["handoff_block_reason"])
        self.assertFalse(rows[0]["can_start_stage"])

        repository.orders["DCO-1"]["approved_plan"] = "PLAN-1"
        rows = queries.get_my_inbox(repository)
        self.assertTrue(rows[0]["can_handoff_stage"])
        self.assertEqual(rows[0]["handoff_block_code"], "")

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

    def test_dispatch_options_mark_physical_route_blocked_until_plan_approval(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-1",
            status="Approved",
            production_path=None,
            current_production_stage=None,
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
            approved_plan=None,
        )

        result = queries.get_dispatch_options(repository, "DCO-1")
        by_name = {row["value"]: row for row in result["paths"]}
        self.assertFalse(by_name["Sharyoun"]["can_dispatch"])
        self.assertIn("اعتماد خطة القص", by_name["Sharyoun"]["dispatch_block_reason"])
        self.assertTrue(by_name["Drawing"]["can_dispatch"])
        self.assertTrue(by_name["Drawing"]["starts_with_planning"])
        self.assertTrue(by_name["Drawing"]["stages"][0]["is_planning_stage"])

        repository.order.approved_plan = "PLAN-1"
        result = queries.get_dispatch_options(repository, "DCO-1")
        self.assertTrue(all(row["can_dispatch"] for row in result["paths"]))

        repository.capabilities.remove(Capability.DISPATCH_ORDER)
        with self.assertRaises(queries.ShopFloorPermissionDenied):
            queries.get_dispatch_options(repository, "DCO-1")

    def test_order_detail_uses_route_planning_gate_and_document_capabilities(self) -> None:
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
                "operational_role": "عامل رسم",
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
        self.assertEqual(detail["stage_snapshot"]["can_handoff_to"], "CNC")
        self.assertFalse(detail["stage_snapshot"]["can_handoff_stage"])
        self.assertEqual(detail["stage_snapshot"]["handoff_block_code"], "plan_not_approved")
        self.assertFalse(actions[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"])
        self.assertTrue(detail["stage_snapshot"]["can_reassign_worker"])
        self.assertTrue(detail["can_recalculate_drawing_plan"])
        self.assertTrue(detail["document_capabilities"][Capability.VIEW_CUTTING_PLAN])

        repository.order.approved_plan = "PLAN-1"
        detail = queries.get_order_detail(repository, "DCO-2")
        self.assertTrue(detail["stage_snapshot"]["can_handoff_stage"])
        self.assertFalse(detail["can_recalculate_drawing_plan"])

    def test_any_configured_planning_stage_enables_recalculation_without_drawing_name(self) -> None:
        repository = FakeRepository()
        repository.routes["Custom Route"] = ProductionRoute(
            "Custom Route",
            "مسار مخصص",
            (RoutingStage(10, "PlanningDesk", "التخطيط", "مصمم مخصص", True),),
        )
        repository.order = SimpleNamespace(
            name="DCO-2",
            status="Production In Progress",
            production_path="Custom Route",
            current_production_stage="PST-2",
            approved_plan=None,
            approved_plan_source="System",
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
        )
        repository.stage_summaries["PST-2"] = {
            "name": "PST-2",
            "status": "In Progress",
            "stage_type": "PlanningDesk",
            "assigned_to": repository.user,
            "operational_role": "مصمم مخصص",
        }

        detail = queries.get_order_detail(repository, "DCO-2")
        self.assertTrue(detail["can_recalculate_drawing_plan"])

    def test_action_context_denies_another_workers_stage(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-2",
            status="At CNC",
            production_path="Drawing",
            current_production_stage="PST-2",
            approved_plan="PLAN-1",
            approved_plan_source="System",
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
        )
        repository.stage_summaries = {
            "PST-2": {
                "name": "PST-2",
                "status": "Pending",
                "stage_type": "CNC",
                "assigned_to": "other@example.com",
                "operational_role": "عامل CNC",
            }
        }

        detail = queries.get_order_detail(repository, "DCO-2")
        actions = detail["stage_snapshot"]["production_actions"]

        self.assertFalse(detail["stage_snapshot"]["can_start_stage"])
        self.assertEqual(actions[Capability.START_ASSIGNED_STAGE]["code"], "not_assigned")
        self.assertTrue(detail["stage_snapshot"]["can_reassign_worker"])

    def test_minimal_current_stage_context_is_route_aware_and_data_minimal(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-2",
            status="At CNC",
            production_path="Drawing",
            current_production_stage="PST-2",
            approved_plan="PLAN-1",
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
        )
        repository.stage_summaries["PST-2"] = {
            "name": "PST-2",
            "status": "Pending",
            "stage_type": "CNC",
            "assigned_to": repository.user,
            "operational_role": "عامل CNC",
        }

        context = queries.get_current_stage_context(repository, "DCO-2")

        self.assertEqual(context["active_stage_name"], "PST-2")
        self.assertTrue(context["can_start_stage"])
        self.assertEqual(
            [stage["department"] for stage in context["route_stages"]],
            ["رسم", "CNC", "تقشيط"],
        )
        self.assertTrue(context["route_stages"][0]["is_planning_stage"])
        self.assertNotIn("cutting_plan_json", context)

    def test_revert_targets_are_unique_and_permission_protected(self) -> None:
        repository = FakeRepository()
        repository.order = SimpleNamespace(
            name="DCO-1",
            status="At CNC",
            production_path="Drawing",
            current_production_stage="PST-3",
            cutting_plan_json='{"sheets":[{}]}',
            plan_needs_recalculation=0,
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
