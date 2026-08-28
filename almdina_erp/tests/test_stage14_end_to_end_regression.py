from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime
from typing import Any, Sequence

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
    build_internal_cost_report_document,
)
from almdina_erp.almdina_erp.application.security.business_capability_state import (
    normalize_business_capability_state,
)
from almdina_erp.almdina_erp.application.shop_floor import commands, queries
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.domain.security.authorization import ALL_CAPABILITIES, Capability


class StatefulFactoryRepository:
    """One in-memory factory used by commands and queries in the same journey.

    This deliberately models only persistence/identity ports. Business decisions
    stay inside the real application/domain functions exercised by the tests.
    """

    def __init__(self) -> None:
        self.actor = "supervisor@example.com"
        self.orders: dict[str, commands.OrderState] = {}
        self.stages: dict[str, commands.StageState] = {}
        self.events: list[tuple[str, str, dict[str, Any]]] = []
        self._counter = 0
        self.routes = {
            "Drawing": ProductionRoute(
                "Drawing",
                "رسم وCNC وتقشيط",
                (
                    RoutingStage(10, "Drawing", "رسم", "عامل رسم", True),
                    RoutingStage(20, "CNC", "CNC", "عامل CNC"),
                    RoutingStage(30, "Sanding", "تقشيط", "عامل تقشيط"),
                ),
            )
        }
        self.profiles: dict[str, dict[str, Any]] = {
            "supervisor@example.com": {
                "roles": ("مشرف إنتاج",),
                "capabilities": {
                    Capability.VIEW_ORDERS,
                    Capability.DISPATCH_ORDER,
                    Capability.REASSIGN_WORKER,
                    Capability.MARK_DELIVERED,
                    Capability.VIEW_OPERATIONAL_REPORTS,
                },
            },
            "drawing@example.com": {
                "roles": ("عامل رسم",),
                "capabilities": {
                    Capability.VIEW_ORDERS,
                    Capability.VIEW_CUTTING_PLAN,
                    Capability.RECALCULATE_PLAN,
                    Capability.VIEW_DRAWING_WORKSPACE,
                    Capability.EXPORT_DXF,
                    Capability.UPLOAD_DXF,
                    Capability.START_ASSIGNED_STAGE,
                    Capability.HANDOFF_ASSIGNED_STAGE,
                    Capability.VIEW_SHOP_FLOOR_HISTORY,
                },
            },
            "cnc@example.com": {
                "roles": ("عامل CNC",),
                "capabilities": {
                    Capability.VIEW_ORDERS,
                    Capability.VIEW_CUTTING_PLAN,
                    Capability.START_ASSIGNED_STAGE,
                    Capability.HANDOFF_ASSIGNED_STAGE,
                    Capability.VIEW_SHOP_FLOOR_HISTORY,
                },
            },
            "edge@example.com": {
                "roles": ("عامل تقشيط",),
                "capabilities": {
                    Capability.VIEW_ORDERS,
                    Capability.START_ASSIGNED_STAGE,
                    Capability.HANDOFF_ASSIGNED_STAGE,
                    Capability.VIEW_SHOP_FLOOR_HISTORY,
                },
            },
            "financial@example.com": {
                "roles": ("Finance",),
                "capabilities": {
                    Capability.VIEW_ORDERS,
                    Capability.VIEW_COSTS,
                    Capability.VIEW_FINANCIAL_REPORTS,
                    Capability.PRINT_INTERNAL_COST_REPORT,
                },
            },
            "permission-admin@example.com": {
                "roles": ("Permission Admin",),
                "capabilities": {Capability.MANAGE_PERMISSIONS},
            },
            "system-manager@example.com": {
                "roles": ("System Manager",),
                "capabilities": set(),
            },
            "Administrator": {
                "roles": ("System Manager",),
                "capabilities": set(ALL_CAPABILITIES),
            },
        }

    def as_actor(self, user: str) -> None:
        self.actor = user

    def _profile(self, user: str | None = None) -> dict[str, Any]:
        return self.profiles.get(user or self.actor, {"roles": (), "capabilities": set()})

    # Shared identity / authorization ports ---------------------------------
    def current_user(self) -> str:
        return self.actor

    def capabilities_for_order(self, order: Any) -> frozenset[str]:
        return frozenset(self._profile()["capabilities"])

    def global_capabilities(self) -> frozenset[str]:
        return frozenset(self._profile()["capabilities"])

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]:
        return tuple(self._profile(user)["roles"])

    def is_admin(self, user: str | None = None) -> bool:
        actor = user or self.actor
        if actor == "Administrator":
            return True
        capabilities = set(self._profile(actor)["capabilities"])
        return bool(
            capabilities.intersection(
                {
                    Capability.REASSIGN_WORKER,
                    Capability.REVERT_DEPARTMENT,
                    Capability.MARK_DELIVERED,
                }
            )
        )

    def session_identity(self) -> dict[str, Any]:
        return {"user": self.actor, "full_name": self.actor, "roles": list(self.actor_roles())}

    # Routing ---------------------------------------------------------------
    def list_active_routes(self) -> list[ProductionRoute]:
        return list(self.routes.values())

    def get_production_route(self, route_name: str) -> ProductionRoute:
        try:
            return self.routes[route_name]
        except KeyError as error:
            raise ValueError(f"Unknown production route: {route_name}") from error

    def assert_worker_for_role(self, user: str, role: str) -> None:
        if role not in self.actor_roles(user):
            raise commands.ShopFloorCommandError("العامل المختار لا يملك دور المرحلة المطلوبة.")

    def get_users_for_role(self, role: str) -> list[dict[str, str]]:
        return [
            {"name": user, "full_name": user}
            for user in sorted(self.profiles)
            if role in self.actor_roles(user)
        ]

    def default_production_route(self) -> str | None:
        return "Drawing"

    # Command persistence port ---------------------------------------------
    def lock_order(self, order_name: str) -> None:
        return None

    def lock_stage(self, stage_name: str) -> None:
        return None

    def get_order_state(self, order_name: str) -> commands.OrderState:
        return self.orders[order_name]

    def get_stage_state(self, stage_name: str) -> commands.StageState:
        return self.stages[stage_name]

    def validate_special_shapes(self, order_name: str) -> None:
        return None

    def cancel_active_order_stages(self, order_name: str) -> None:
        for name, stage in list(self.stages.items()):
            if stage.order_name == order_name and stage.status not in {"Completed", "Cancelled"}:
                self.stages[name] = replace(stage, status="Cancelled")

    def create_stage(
        self,
        *,
        order_name: str,
        stage_type: str,
        assignee: str,
        sequence: int,
        department_label: str | None = None,
        operational_role: str | None = None,
    ) -> commands.StageState:
        self._counter += 1
        stage = commands.StageState(
            name=f"PST-E2E-{self._counter}",
            order_name=order_name,
            stage_type=stage_type,
            status="Pending",
            assigned_to=assignee,
            sequence=sequence,
            department_label=department_label,
            operational_role=operational_role,
        )
        self.stages[stage.name] = stage
        return stage

    def reassign_stage(self, stage_name: str, *, assignee: str) -> commands.StageState:
        updated = replace(self.stages[stage_name], assigned_to=assignee)
        self.stages[stage_name] = updated
        return updated

    def track_order_to_stage(
        self,
        order_name: str,
        *,
        stage_name: str,
        path: str | None = None,
    ) -> None:
        order = self.orders[order_name]
        stage = self.stages[stage_name]
        self.orders[order_name] = replace(
            order,
            production_path=path if path is not None else order.production_path,
            current_stage=stage_name,
            status=commands.order_status_for_stage_type(stage.stage_type),
        )

    def track_order_ready_for_delivery(self, order_name: str) -> None:
        self.orders[order_name] = replace(
            self.orders[order_name], status="Ready for Delivery", current_stage=None
        )

    def track_order_delivered(self, order_name: str) -> None:
        self.orders[order_name] = replace(
            self.orders[order_name], status="Delivered", current_stage=None
        )

    def log_stage_event(
        self,
        stage_name: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append((stage_name, event_type, dict(details or {})))

    def close_open_pause(self, stage_name: str, resumed_by: str) -> None:
        return None

    def start_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
    ) -> commands.StageState:
        stage = self.stages[stage_name]
        updated = replace(
            stage,
            status=target_status,
            assigned_to=stage.assigned_to or actor,
            start_time=datetime(2026, 8, 16, 9, 0, 0),
        )
        self.stages[stage_name] = updated
        return updated

    def complete_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
        completed_qty: int,
    ) -> commands.StageState:
        updated = replace(self.stages[stage_name], status=target_status)
        self.stages[stage_name] = updated
        return updated

    def required_piece_qty(self, order_name: str) -> int:
        return 7

    def get_order_status(self, order_name: str) -> str | None:
        return self.orders[order_name].status

    def list_revert_candidates(
        self, order_name: str, stage_type: str
    ) -> Sequence[commands.StageState]:
        return [
            stage
            for stage in self.stages.values()
            if stage.order_name == order_name and stage.stage_type == stage_type
        ]

    def stage_exists(self, stage_name: str | None) -> bool:
        return bool(stage_name and stage_name in self.stages)

    def list_later_stages(
        self, order_name: str, sequence: int
    ) -> Sequence[commands.StageState]:
        return sorted(
            (
                stage
                for stage in self.stages.values()
                if stage.order_name == order_name and stage.sequence > sequence
            ),
            key=lambda row: row.sequence,
        )

    def cancel_stage(self, stage_name: str, *, target_status: str) -> commands.StageState:
        updated = replace(self.stages[stage_name], status=target_status)
        self.stages[stage_name] = updated
        return updated

    def reopen_stage(self, stage_name: str, *, target_status: str) -> commands.StageState:
        updated = replace(self.stages[stage_name], status=target_status)
        self.stages[stage_name] = updated
        return updated

    # Query persistence port ------------------------------------------------
    def _stage_row(self, stage: commands.StageState) -> dict[str, Any]:
        return {
            "name": stage.name,
            "door_cutting_order": stage.order_name,
            "stage_type": stage.stage_type,
            "status": stage.status,
            "assigned_to": stage.assigned_to,
            "sequence": stage.sequence,
            "department_label": stage.department_label,
            "operational_role": stage.operational_role,
        }

    def _order_row(self, order: commands.OrderState) -> dict[str, Any]:
        current = self.stages.get(order.current_stage or "")
        return {
            "name": order.name,
            "customer": "زبون اختبار E2E",
            "order_date": "2026-08-16",
            "board_description": "MDF أبيض 18 مم",
            "edge_color": "أبيض",
            "status": order.status,
            "production_path": order.production_path,
            "current_production_stage": order.current_stage,
            "current_department": current.department_label if current else None,
            "department_status": "قيد العمل" if current and current.status == "In Progress" else "بحاجة للعمل",
            "approved_plan": "PLAN-E2E-1" if order.has_approved_plan else None,
            "plan_needs_recalculation": int(order.plan_needs_recalculation),
            "drawing_dxf_status": order.drawing_dxf_status,
            "revision": 1,
        }

    def list_inbox_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        rows = [
            stage
            for stage in self.stages.values()
            if stage.status not in {"Completed", "Cancelled"}
            and (is_admin or stage.assigned_to == user)
        ]
        return [self._stage_row(stage) for stage in rows]

    def list_archive_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        rows = [
            stage
            for stage in self.stages.values()
            if stage.status == "Completed" and (is_admin or stage.assigned_to == user)
        ]
        return [self._stage_row(stage) for stage in rows]

    def current_stage_names(self, order_names: Sequence[str]) -> dict[str, str | None]:
        return {name: self.orders[name].current_stage for name in order_names if name in self.orders}

    def order_summaries(self, order_names: Sequence[str]) -> dict[str, Any]:
        return {
            name: self._order_row(self.orders[name])
            for name in order_names
            if name in self.orders
        }

    def personal_order_stage_timings(
        self, order_names: Sequence[str], *, user: str
    ) -> dict[str, Any]:
        return {}

    def get_order(self, order_name: str) -> Any:
        return self._order_row(self.orders[order_name])

    def can_view_order(self, order: Any) -> bool:
        return self.is_admin() or Capability.VIEW_ORDERS in self.global_capabilities()

    def list_order_stages(self, order_name: str) -> list[Any]:
        return [
            self._stage_row(stage)
            for stage in sorted(self.stages.values(), key=lambda row: row.sequence)
            if stage.order_name == order_name
        ]

    def get_stage_summary(self, stage_name: str) -> Any | None:
        stage = self.stages.get(stage_name)
        return self._stage_row(stage) if stage else None

    def load_plan_snapshot(
        self, order: Any, plan_source: str | None = None
    ) -> dict[str, Any]:
        return {"sheets": [{"index": 1, "placements": []}]}

    def user_can_view_dual_plans(self) -> bool:
        return Capability.VIEW_CUTTING_PLAN in self.global_capabilities()

    def list_revert_stages(self, order_name: str) -> list[Any]:
        return self.list_order_stages(order_name)


class TestStage14EndToEndRegression(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = StatefulFactoryRepository()
        self.repository.orders["DCO-E2E-1"] = commands.OrderState(
            name="DCO-E2E-1",
            status="Approved",
            production_path=None,
            current_stage=None,
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=False,
        )

    def test_order_moves_drawing_to_cnc_to_edge_then_delivery_with_personal_history(self) -> None:
        repository = self.repository

        repository.as_actor("supervisor@example.com")
        dispatched = commands.dispatch_order(
            repository, "DCO-E2E-1", "Drawing", "drawing@example.com"
        )
        drawing_stage = dispatched["stage"]
        self.assertEqual(repository.orders["DCO-E2E-1"].status, "At Drawing")

        repository.as_actor("drawing@example.com")
        self.assertEqual([row["name"] for row in queries.get_my_inbox(repository)], [drawing_stage])
        commands.start_my_stage(repository, drawing_stage)
        with self.assertRaisesRegex(commands.ShopFloorCommandError, "اعتمد خطة القص"):
            commands.handoff_to_next(repository, drawing_stage, "cnc@example.com")

        repository.orders["DCO-E2E-1"] = replace(
            repository.orders["DCO-E2E-1"], has_approved_plan=True
        )
        drawing_handoff = commands.handoff_to_next(
            repository, drawing_stage, "cnc@example.com"
        )
        cnc_stage = drawing_handoff["next_stage"]
        self.assertEqual(repository.orders["DCO-E2E-1"].status, "At CNC")
        self.assertEqual(queries.get_my_inbox(repository), [])
        self.assertEqual(
            [row["name"] for row in queries.get_my_archive(repository)], [drawing_stage]
        )

        repository.as_actor("edge@example.com")
        self.assertEqual(queries.get_my_inbox(repository), [])
        with self.assertRaises(commands.ShopFloorCommandError):
            commands.start_my_stage(repository, cnc_stage)

        repository.as_actor("financial@example.com")
        with self.assertRaises(commands.ShopFloorPermissionDenied):
            commands.start_my_stage(repository, cnc_stage)

        repository.as_actor("cnc@example.com")
        self.assertEqual([row["name"] for row in queries.get_my_inbox(repository)], [cnc_stage])
        commands.start_my_stage(repository, cnc_stage)
        cnc_handoff = commands.handoff_to_next(repository, cnc_stage, "edge@example.com")
        edge_stage = cnc_handoff["next_stage"]
        self.assertEqual(repository.orders["DCO-E2E-1"].status, "At Sanding")
        self.assertEqual(
            [row["name"] for row in queries.get_my_archive(repository)], [cnc_stage]
        )

        repository.as_actor("edge@example.com")
        self.assertEqual([row["name"] for row in queries.get_my_inbox(repository)], [edge_stage])
        commands.start_my_stage(repository, edge_stage)
        final = commands.handoff_to_next(repository, edge_stage)
        self.assertTrue(final["ready_for_delivery"])
        self.assertEqual(repository.orders["DCO-E2E-1"].status, "Ready for Delivery")
        self.assertEqual(queries.get_my_inbox(repository), [])
        self.assertEqual(queries.get_my_archive(repository), [])

        repository.as_actor("supervisor@example.com")
        self.assertEqual(
            [row["name"] for row in queries.get_ready_for_delivery(repository)],
            [edge_stage],
        )
        commands.mark_delivered(repository, "DCO-E2E-1")
        self.assertEqual(repository.orders["DCO-E2E-1"].status, "Delivered")
        self.assertEqual(
            [event[1] for event in repository.events].count("Finish"), 3
        )

        repository.as_actor("edge@example.com")
        self.assertEqual(
            [row["name"] for row in queries.get_my_archive(repository)], [edge_stage]
        )

    def test_finance_permission_admin_and_system_manager_cannot_enter_production_by_role_name(self) -> None:
        repository = self.repository
        for actor in (
            "financial@example.com",
            "permission-admin@example.com",
            "system-manager@example.com",
        ):
            with self.subTest(actor=actor):
                repository.as_actor(actor)
                with self.assertRaises(commands.ShopFloorPermissionDenied):
                    commands.dispatch_order(
                        repository, "DCO-E2E-1", "Drawing", "drawing@example.com"
                    )
                self.assertIsNone(repository.orders["DCO-E2E-1"].current_stage)

    def test_customer_sales_document_stays_available_without_exposing_internal_cost(self) -> None:
        order_entry_state = normalize_business_capability_state(
            {
                Capability.VIEW_ORDERS: True,
                Capability.CREATE_ORDER: True,
                Capability.EDIT_ORDER: True,
                Capability.PRINT_CUSTOMER_INVOICE: True,
            }
        )
        financial_state = normalize_business_capability_state(
            {
                Capability.VIEW_ORDERS: True,
                Capability.VIEW_COSTS: True,
                Capability.PRINT_INTERNAL_COST_REPORT: True,
                Capability.VIEW_FINANCIAL_REPORTS: True,
            }
        )
        self.assertTrue(order_entry_state[Capability.PRINT_CUSTOMER_INVOICE])
        self.assertFalse(order_entry_state[Capability.VIEW_COSTS])
        self.assertTrue(financial_state[Capability.VIEW_COSTS])
        self.assertFalse(financial_state[Capability.DISPATCH_ORDER])

        order = {
            "name": "DCO-E2E-PRICE",
            "customer": "زبون E2E",
            "order_date": "2026-08-16",
            "board_description": "MDF أبيض 18 مم",
            "edge_color": "أبيض",
            "revision": 1,
            "required_boards": 2,
            "board_rate_usd": 20,
            "cutting_cost_per_board_usd": 3,
            "mdf_cost_usd": 40,
            "cutting_cost_usd": 6,
            "edge_cost_usd": 4,
            "total_cost_usd": 50,
            "customer_quote_total_usd": 80,
            "actual_cost_usd": 50,
        }
        pieces = [
            {
                "piece_no": 1,
                "piece_type": "Regular",
                "width_cm": 50,
                "length_cm": 100,
                "qty": 2,
                "edge_type": "2cm عادي",
                "edge_meters": 8,
                "edge_rate_usd": 0.5,
                "edge_cost_usd": 4,
            }
        ]

        customer_document = build_customer_invoice_document(order, pieces)
        self.assertEqual(customer_document["kind"], "customer_invoice")
        self.assertNotIn("cost_breakdown", customer_document)
        self.assertNotIn("classification", customer_document)
        self.assertGreater(customer_document["totals"][0]["value_usd"], 0)

        internal_document = build_internal_cost_report_document(order, pieces)
        self.assertEqual(internal_document["kind"], "internal_cost_report")
        self.assertIn("classification", internal_document)
        self.assertIn("cost_breakdown", internal_document)


if __name__ == "__main__":
    unittest.main()
