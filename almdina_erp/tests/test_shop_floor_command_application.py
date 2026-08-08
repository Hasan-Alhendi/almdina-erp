from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime
from typing import Any, Sequence

from almdina_erp.almdina_erp.application.shop_floor import commands
from almdina_erp.almdina_erp.domain.orders.production_authorization import PRODUCTION_ACTIONS
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class FakeShopFloorCommandRepository:
    def __init__(self) -> None:
        self.actor = "worker@example.com"
        self.capabilities = set(PRODUCTION_ACTIONS)
        self.orders: dict[str, commands.OrderState] = {}
        self.stages: dict[str, commands.StageState] = {}
        self.users: dict[str, list[dict[str, str]]] = {}
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
        self.calls: list[tuple[Any, ...]] = []
        self._counter = 0

    def current_user(self) -> str:
        return self.actor

    def capabilities_for_order(self, order_name: str) -> frozenset[str]:
        self.calls.append(("capabilities_for_order", order_name))
        return frozenset(self.capabilities)

    def lock_order(self, order_name: str) -> None:
        self.calls.append(("lock_order", order_name))

    def lock_stage(self, stage_name: str) -> None:
        self.calls.append(("lock_stage", stage_name))

    def get_order_state(self, order_name: str) -> commands.OrderState:
        return self.orders[order_name]

    def get_stage_state(self, stage_name: str) -> commands.StageState:
        return self.stages[stage_name]

    def validate_special_shapes(self, order_name: str) -> None:
        self.calls.append(("validate_special_shapes", order_name))

    def get_production_route(self, route_name: str) -> ProductionRoute:
        return self.routes[route_name]

    def assert_worker_for_role(self, user: str, role: str) -> None:
        self.calls.append(("assert_worker_for_role", user, role))

    def get_users_for_role(self, role: str) -> list[dict[str, str]]:
        return list(self.users.get(role, []))

    def cancel_active_order_stages(self, order_name: str) -> None:
        self.calls.append(("cancel_active_order_stages", order_name))

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
            name=f"PST-{self._counter}",
            order_name=order_name,
            stage_type=stage_type,
            status="Pending",
            assigned_to=assignee,
            sequence=sequence,
            department_label=department_label,
            operational_role=operational_role,
        )
        self.stages[stage.name] = stage
        self.calls.append(("create_stage", order_name, stage_type, assignee, sequence))
        return stage

    def reassign_stage(self, stage_name: str, *, assignee: str) -> commands.StageState:
        updated = replace(self.stages[stage_name], assigned_to=assignee)
        self.stages[stage_name] = updated
        self.calls.append(("reassign_stage", stage_name, assignee))
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
        self.calls.append(("track_order_to_stage", order_name, stage_name, path))

    def track_order_ready_for_delivery(self, order_name: str) -> None:
        self.orders[order_name] = replace(
            self.orders[order_name], status="Ready for Delivery", current_stage=None
        )
        self.calls.append(("track_order_ready_for_delivery", order_name))

    def track_order_delivered(self, order_name: str) -> None:
        self.orders[order_name] = replace(
            self.orders[order_name], status="Delivered", current_stage=None
        )
        self.calls.append(("track_order_delivered", order_name))

    def log_stage_event(
        self,
        stage_name: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append(("log_stage_event", stage_name, event_type, details or {}))

    def close_open_pause(self, stage_name: str, resumed_by: str) -> None:
        self.calls.append(("close_open_pause", stage_name, resumed_by))

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
            start_time=datetime(2026, 1, 1, 8, 0, 0),
        )
        self.stages[stage_name] = updated
        self.calls.append(("start_stage", stage_name, actor, target_status))
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
        self.calls.append(("complete_stage", stage_name, actor, target_status, completed_qty))
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
            key=lambda stage: stage.sequence,
        )

    def cancel_stage(self, stage_name: str, *, target_status: str) -> commands.StageState:
        updated = replace(self.stages[stage_name], status=target_status)
        self.stages[stage_name] = updated
        self.calls.append(("cancel_stage", stage_name, target_status))
        return updated

    def reopen_stage(self, stage_name: str, *, target_status: str) -> commands.StageState:
        updated = replace(self.stages[stage_name], status=target_status)
        self.stages[stage_name] = updated
        self.calls.append(("reopen_stage", stage_name, target_status))
        return updated


class TestShopFloorCommandApplication(unittest.TestCase):
    @staticmethod
    def _approved_order(
        name: str = "DCO-1", *, plan_approved: bool = True
    ) -> commands.OrderState:
        return commands.OrderState(
            name=name,
            status="Approved",
            production_path=None,
            current_stage=None,
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=plan_approved,
        )

    @staticmethod
    def _call_index(repository: FakeShopFloorCommandRepository, name: str) -> int:
        return next(index for index, call in enumerate(repository.calls) if call[0] == name)

    def test_planning_first_dispatch_locks_order_and_can_start_before_plan_approval(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = self._approved_order(plan_approved=False)

        result = commands.dispatch_order(
            repository, "DCO-1", "Drawing", "drawing@example.com"
        )

        self.assertEqual(result["status"], "At Drawing")
        self.assertEqual(result["stage"], "PST-1")
        self.assertLess(
            self._call_index(repository, "lock_order"),
            self._call_index(repository, "create_stage"),
        )
        self.assertIn(("validate_special_shapes", "DCO-1"), repository.calls)
        self.assertIn(
            ("assert_worker_for_role", "drawing@example.com", "عامل رسم"),
            repository.calls,
        )

    def test_physical_first_route_requires_approved_plan_before_dispatch(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = self._approved_order(plan_approved=False)

        with self.assertRaisesRegex(commands.ShopFloorCommandError, "اعتماد خطة القص"):
            commands.dispatch_order(
                repository, "DCO-1", "Sharyoun", "cutting@example.com"
            )

        self.assertFalse(any(call[0] == "create_stage" for call in repository.calls))

        repository.calls.clear()
        repository.orders["DCO-1"] = self._approved_order(plan_approved=True)
        result = commands.dispatch_order(
            repository, "DCO-1", "Sharyoun", "cutting@example.com"
        )
        self.assertEqual(result["department"], "شريون")

    def test_custom_route_uses_configured_stage_role_and_department(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.routes["PVC Route"] = ProductionRoute(
            "PVC Route",
            "مسار PVC",
            (
                RoutingStage(10, "Cutting", "قص", "عامل قص مخصص"),
                RoutingStage(20, "PVC", "تلبيس PVC", "عامل PVC"),
            ),
        )
        repository.orders["DCO-1"] = self._approved_order()

        result = commands.dispatch_order(
            repository, "DCO-1", "PVC Route", "cutter@example.com"
        )

        self.assertEqual(result["department"], "قص")
        self.assertIn(
            ("assert_worker_for_role", "cutter@example.com", "عامل قص مخصص"),
            repository.calls,
        )
        stage = repository.stages[result["stage"]]
        self.assertEqual(stage.operational_role, "عامل قص مخصص")
        self.assertEqual(stage.department_label, "قص")

    def test_missing_capability_fails_after_lock_but_before_production_write(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.capabilities.remove(Capability.DISPATCH_ORDER)
        repository.orders["DCO-1"] = self._approved_order()

        with self.assertRaises(commands.ShopFloorPermissionDenied):
            commands.dispatch_order(
                repository, "DCO-1", "Drawing", "drawing@example.com"
            )

        self.assertIn(("lock_order", "DCO-1"), repository.calls)
        self.assertFalse(
            any(call[0] in {"create_stage", "track_order_to_stage"} for call in repository.calls)
        )

    def test_start_stage_locks_order_then_stage_and_checks_assignment(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = replace(
            self._approved_order(),
            status="At Sharyoun",
            production_path="Sharyoun",
            current_stage="PST-1",
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="Sharyoun",
            status="Pending",
            assigned_to="other@example.com",
            sequence=10,
        )

        with self.assertRaisesRegex(commands.ShopFloorCommandError, "عامل آخر"):
            commands.start_my_stage(repository, "PST-1")

        self.assertLess(
            self._call_index(repository, "lock_order"),
            self._call_index(repository, "lock_stage"),
        )
        repository.calls.clear()
        repository.stages["PST-1"] = replace(
            repository.stages["PST-1"], assigned_to=repository.actor
        )
        result = commands.start_my_stage(repository, "PST-1")

        self.assertEqual(result["status"], "In Progress")
        self.assertLess(
            self._call_index(repository, "lock_stage"),
            self._call_index(repository, "start_stage"),
        )

    def test_planning_stage_cannot_handoff_until_reviewed_plan_is_approved(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At Drawing",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=False,
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="Drawing",
            status="In Progress",
            assigned_to=repository.actor,
            sequence=10,
        )

        with self.assertRaisesRegex(commands.ShopFloorCommandError, "اعتمد خطة القص"):
            commands.handoff_to_next(repository, "PST-1", "cnc@example.com")
        self.assertFalse(any(call[0] == "complete_stage" for call in repository.calls))

        repository.calls.clear()
        repository.orders["DCO-1"] = replace(
            repository.orders["DCO-1"], has_approved_plan=True
        )
        result = commands.handoff_to_next(repository, "PST-1", "cnc@example.com")
        self.assertEqual(result["next_stage_type"], "CNC")
        self.assertLess(
            self._call_index(repository, "lock_stage"),
            self._call_index(repository, "complete_stage"),
        )

    def test_stale_plan_blocks_planning_handoff_even_when_old_plan_is_approved(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At Drawing",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=True,
            has_approved_plan=True,
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="Drawing",
            status="In Progress",
            assigned_to=repository.actor,
            sequence=10,
        )

        with self.assertRaisesRegex(commands.ShopFloorCommandError, "إعادة حساب واعتماد جديد"):
            commands.handoff_to_next(repository, "PST-1", "cnc@example.com")

    def test_handoff_validates_next_worker_before_completing_current_stage(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At CNC",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=True,
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="CNC",
            status="In Progress",
            assigned_to=repository.actor,
            sequence=20,
        )

        with self.assertRaisesRegex(commands.ShopFloorCommandError, "اختر العامل"):
            commands.handoff_to_next(repository, "PST-1")

        self.assertEqual(repository.stages["PST-1"].status, "In Progress")
        self.assertFalse(any(call[0] == "complete_stage" for call in repository.calls))

    def test_final_handoff_marks_order_ready_for_delivery(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At Sanding",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=True,
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="Sanding",
            status="In Progress",
            assigned_to=repository.actor,
            sequence=30,
        )

        result = commands.handoff_to_next(repository, "PST-1")

        self.assertTrue(result["ready_for_delivery"])
        self.assertEqual(repository.orders["DCO-1"].status, "Ready for Delivery")
        self.assertIn(("track_order_ready_for_delivery", "DCO-1"), repository.calls)

    def test_reassignment_is_locked_independent_and_audited(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At CNC",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=True,
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="CNC",
            status="Pending",
            assigned_to="old@example.com",
            sequence=20,
        )

        result = commands.reassign_worker(repository, "PST-1", "new@example.com")

        self.assertTrue(result["changed"])
        self.assertEqual(result["assigned_to"], "new@example.com")
        self.assertLess(
            self._call_index(repository, "lock_stage"),
            self._call_index(repository, "reassign_stage"),
        )
        self.assertIn(
            ("assert_worker_for_role", "new@example.com", "عامل CNC"),
            repository.calls,
        )
        event = next(
            call
            for call in repository.calls
            if call[:3] == ("log_stage_event", "PST-1", "Override")
        )
        self.assertEqual(event[3]["previous_assignee"], "old@example.com")
        self.assertEqual(event[3]["assignee"], "new@example.com")

    def test_custom_stage_reassignment_workers_use_the_configured_role(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.routes["PVC Route"] = ProductionRoute(
            "PVC Route",
            "مسار PVC",
            (RoutingStage(10, "PVC", "تلبيس PVC", "مشغل PVC"),),
        )
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="Production In Progress",
            production_path="PVC Route",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=True,
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="PVC",
            status="Pending",
            assigned_to="old@example.com",
            sequence=10,
            department_label="تلبيس PVC",
            operational_role="مشغل PVC",
        )
        repository.users["مشغل PVC"] = [
            {"name": "pvc@example.com", "full_name": "عامل PVC"}
        ]

        workers = commands.get_reassignment_workers(repository, "PST-1")
        self.assertEqual(workers[0]["name"], "pvc@example.com")

    def test_revert_locks_order_and_stages_before_mutating_them(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At Sanding",
            production_path="Drawing",
            current_stage="PST-3",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            has_approved_plan=True,
        )
        repository.stages.update(
            {
                "PST-1": commands.StageState("PST-1", "DCO-1", "Drawing", "Completed", "drawing@example.com", 10),
                "PST-2": commands.StageState("PST-2", "DCO-1", "CNC", "Completed", "cnc@example.com", 20),
                "PST-3": commands.StageState("PST-3", "DCO-1", "Sanding", "Pending", "sanding@example.com", 30),
            }
        )

        result = commands.revert_department(
            repository, "DCO-1", target_stage_type="Drawing"
        )

        self.assertEqual(result["stage"], "PST-1")
        self.assertEqual(repository.stages["PST-1"].status, "Pending")
        self.assertEqual(repository.stages["PST-2"].status, "Cancelled")
        self.assertEqual(repository.stages["PST-3"].status, "Cancelled")
        self.assertLess(
            self._call_index(repository, "lock_order"),
            self._call_index(repository, "reopen_stage"),
        )
        self.assertGreaterEqual(
            sum(1 for call in repository.calls if call[0] == "lock_stage"), 3
        )


if __name__ == "__main__":
    unittest.main()
