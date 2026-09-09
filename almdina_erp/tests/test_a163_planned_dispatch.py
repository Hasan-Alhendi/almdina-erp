from __future__ import annotations

import threading
from types import SimpleNamespace
import unittest

from almdina_erp.almdina_erp.application.shop_floor.planned_dispatch import (
    PlannedDispatchError,
    PlannedDispatchPermissionDenied,
    dispatch_planned_order,
    get_planned_dispatch_context,
)
from almdina_erp.almdina_erp.domain.orders.intake_lifecycle import READY_TO_DISPATCH
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def _route(*, planning_first: bool = False, name: str = "ROUTE-A") -> ProductionRoute:
    return ProductionRoute(
        name=name,
        label=f"Route {name}",
        stages=(
            RoutingStage(
                sequence=10,
                stage_type="PLANNING" if planning_first else "LASER",
                department_label="تخطيط" if planning_first else "ليزر",
                operational_role="Planner" if planning_first else "Laser Operator",
                is_planning_stage=planning_first,
            ),
            RoutingStage(
                sequence=20,
                stage_type="EDGE",
                department_label="قشاط",
                operational_role="Edge Operator",
            ),
            RoutingStage(
                sequence=30,
                stage_type="PACKING",
                department_label="توضيب",
                operational_role="Packing Operator",
            ),
        ),
    )


class FakePlannedDispatchRepository:
    def __init__(self, *, planning_first: bool = False) -> None:
        self.actor = "entry@example.com"
        self.admin = False
        self.route = _route(planning_first=planning_first)
        first_role = self.route.first_stage.operational_role
        self.valid_worker = "worker@example.com"
        self.worker_roles = {self.valid_worker: {first_role}}
        self.worker_enabled = {self.valid_worker: True}
        self.capabilities = {Capability.DISPATCH_ORDER}
        self.order = SimpleNamespace(
            name="DCO-1",
            status="Draft",
            workflow_stage=READY_TO_DISPATCH,
            production_path=None,
            current_stage=None,
            current_assignee=self.actor,
            owner=self.actor,
            planned_route=self.route.name,
            planned_assignee=self.valid_worker,
            has_cutting_plan=not planning_first,
            plan_needs_recalculation=False,
            drawing_dxf_status=None,
        )
        self.route_enabled = True
        self.active_stage = False
        self.special_shapes_valid = True
        self.created = []
        self.events = []
        self.calls = []

    def current_user(self) -> str:
        return self.actor

    def is_admin(self, user: str | None = None) -> bool:
        return self.admin

    def capabilities_for_order(self, order_name: str) -> frozenset[str]:
        self.calls.append("capabilities")
        return frozenset(self.capabilities)

    def lock_order(self, order_name: str) -> None:
        assert order_name == self.order.name
        self.calls.append("lock_order")

    def get_planned_dispatch_order(self, order_name: str):
        assert order_name == self.order.name
        self.calls.append("get_order")
        return self.order

    def get_production_route(self, route_name: str) -> ProductionRoute:
        self.calls.append("get_route")
        if not self.route_enabled:
            raise ValueError(f"مسار الإنتاج {route_name} معطّل.")
        if route_name != self.route.name:
            raise ValueError("مسار الإنتاج غير موجود.")
        return self.route

    def assert_worker_for_role(self, user: str, role: str) -> None:
        self.calls.append("assert_worker")
        if not self.worker_enabled.get(user, False):
            raise ValueError("العامل المحدد غير مفعّل.")
        if role not in self.worker_roles.get(user, set()):
            raise ValueError("العامل المحدد غير مؤهل للمرحلة الأولى.")

    def validate_special_shapes(self, order_name: str) -> None:
        self.calls.append("special_shapes")
        if not self.special_shapes_valid:
            raise ValueError("يجب توثيق الدرف الخاصة قبل الإرسال.")

    def has_active_order_stage(self, order_name: str) -> bool:
        self.calls.append("active_stage")
        return self.active_stage

    def create_stage(self, **values):
        self.calls.append("create_stage")
        stage = SimpleNamespace(
            name=f"PST-{len(self.created) + 1}",
            status="Pending",
            **values,
        )
        self.created.append(stage)
        self.active_stage = True
        return stage

    def activate_planned_dispatch(self, order_name: str, *, path: str, stage_name: str) -> None:
        self.calls.append("activate")
        self.order.workflow_stage = None
        self.order.production_path = path
        self.order.current_stage = stage_name
        self.order.current_assignee = self.order.planned_assignee

    def log_stage_event(self, stage_name: str, event_type: str, details=None) -> None:
        self.calls.append("event")
        self.events.append((stage_name, event_type, details or {}))


class ConcurrentPlannedDispatchRepository(FakePlannedDispatchRepository):
    """Model the row-lock serialization boundary used by the Frappe adapter."""

    def __init__(self) -> None:
        super().__init__()
        self._sequence_guard = threading.Lock()
        self._lock_sequence = 0
        self._first_committed = threading.Event()

    def lock_order(self, order_name: str) -> None:
        with self._sequence_guard:
            self._lock_sequence += 1
            sequence = self._lock_sequence
        if sequence > 1:
            if not self._first_committed.wait(timeout=2):
                raise AssertionError("simulated first transaction did not complete")
        super().lock_order(order_name)

    def log_stage_event(self, stage_name: str, event_type: str, details=None) -> None:
        try:
            super().log_stage_event(stage_name, event_type, details)
        finally:
            self._first_committed.set()


class PlannedDispatchTests(unittest.TestCase):
    def test_valid_persisted_plan_starts_exactly_first_dynamic_stage(self) -> None:
        repository = FakePlannedDispatchRepository()

        result = dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.calls[0:2], ["lock_order", "get_order"])
        self.assertEqual(result["production_path"], "ROUTE-A")
        self.assertEqual(result["stage"], "PST-1")
        self.assertEqual(result["department"], "ليزر")
        self.assertEqual(result["current_assignee"], repository.valid_worker)
        self.assertEqual(repository.order.workflow_stage, None)
        self.assertEqual(repository.order.current_stage, "PST-1")
        self.assertEqual(len(repository.created), 1)
        self.assertEqual(repository.created[0].stage_type, "LASER")
        self.assertEqual(repository.created[0].sequence, 10)
        self.assertEqual(repository.created[0].operational_role, "Laser Operator")
        event = repository.events[0][2]
        self.assertTrue(event["planned_dispatch"])
        self.assertEqual(event["path"], "ROUTE-A")
        self.assertEqual(event["first_stage_type"], "LASER")
        self.assertEqual(event["assignee"], repository.valid_worker)
        self.assertEqual(event["dispatch_actor"], repository.actor)

    def test_context_is_read_only_and_uses_persisted_plan(self) -> None:
        repository = FakePlannedDispatchRepository()

        payload = get_planned_dispatch_context(repository, repository.order.name)

        self.assertEqual(payload["planned_production_route"], "ROUTE-A")
        self.assertEqual(payload["planned_first_assignee"], repository.valid_worker)
        self.assertEqual(payload["route"]["first_stage"]["stage_type"], "LASER")
        self.assertEqual([row["stage_type"] for row in payload["route"]["stages"]], ["LASER", "EDGE", "PACKING"])
        self.assertEqual(repository.created, [])

    def test_wrong_lifecycle_stage_is_rejected_before_creation(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.order.workflow_stage = "DATA_ENTRY"

        with self.assertRaises(PlannedDispatchError):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_non_owner_is_rejected_even_with_role_independent_capability(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.actor = "other@example.com"

        with self.assertRaises(PlannedDispatchPermissionDenied):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_missing_dispatch_capability_is_denied_server_side(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.capabilities.clear()

        with self.assertRaises(PlannedDispatchPermissionDenied):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_missing_persisted_plan_is_rejected(self) -> None:
        for field in ("planned_route", "planned_assignee"):
            with self.subTest(field=field):
                repository = FakePlannedDispatchRepository()
                setattr(repository.order, field, None)
                with self.assertRaises(PlannedDispatchError):
                    dispatch_planned_order(repository, repository.order.name)
                self.assertEqual(repository.created, [])

    def test_disabled_route_between_planning_and_dispatch_is_rejected(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.route_enabled = False

        with self.assertRaises(PlannedDispatchError):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_disabled_worker_between_planning_and_dispatch_is_rejected(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.worker_enabled[repository.valid_worker] = False

        with self.assertRaisesRegex(PlannedDispatchError, "غير مفعّل"):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_worker_role_removed_between_planning_and_dispatch_is_rejected(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.worker_roles[repository.valid_worker].clear()

        with self.assertRaises(PlannedDispatchError):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_hidden_active_route_stage_fails_closed_without_cancellation_or_recreation(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.active_stage = True

        with self.assertRaisesRegex(PlannedDispatchError, "سجل إنتاج نشط"):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])
        self.assertNotIn("activate", repository.calls)

    def test_identical_retry_after_success_cannot_create_second_first_stage(self) -> None:
        repository = FakePlannedDispatchRepository()
        dispatch_planned_order(repository, repository.order.name)

        with self.assertRaises(PlannedDispatchError):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(len(repository.created), 1)

    def test_concurrent_dispatches_serialize_to_one_first_stage(self) -> None:
        repository = ConcurrentPlannedDispatchRepository()
        start = threading.Barrier(3)
        successes: list[dict] = []
        failures: list[Exception] = []

        def attempt() -> None:
            start.wait()
            try:
                successes.append(dispatch_planned_order(repository, repository.order.name))
            except Exception as error:  # exercise the competing transaction result
                failures.append(error)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        start.wait()
        for thread in threads:
            thread.join(timeout=3)

        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], PlannedDispatchError)
        self.assertEqual(len(repository.created), 1)
        self.assertEqual(repository.calls.count("lock_order"), 2)

    def test_physical_first_route_requires_current_cutting_plan_policy(self) -> None:
        repository = FakePlannedDispatchRepository(planning_first=False)
        repository.order.has_cutting_plan = False

        with self.assertRaisesRegex(PlannedDispatchError, "خطة القص"):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_physical_first_route_rejects_stale_cutting_plan(self) -> None:
        repository = FakePlannedDispatchRepository(planning_first=False)
        repository.order.plan_needs_recalculation = True

        with self.assertRaisesRegex(PlannedDispatchError, "أعد حساب خطة القص"):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_planning_first_route_can_receive_order_before_cutting_plan_exists(self) -> None:
        repository = FakePlannedDispatchRepository(planning_first=True)
        repository.order.has_cutting_plan = False

        result = dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(result["stage"], "PST-1")
        self.assertEqual(repository.created[0].stage_type, "PLANNING")

    def test_special_shape_gate_is_preserved(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.special_shapes_valid = False

        with self.assertRaisesRegex(PlannedDispatchError, "الدرف الخاصة"):
            dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(repository.created, [])

    def test_arbitrary_dynamic_route_names_need_no_business_code_changes(self) -> None:
        repository = FakePlannedDispatchRepository()
        repository.route = _route(name="ROUTE-LASER-EDGE-PACK")
        repository.order.planned_route = repository.route.name
        repository.worker_roles = {
            repository.valid_worker: {repository.route.first_stage.operational_role}
        }
        repository.worker_enabled = {repository.valid_worker: True}

        result = dispatch_planned_order(repository, repository.order.name)

        self.assertEqual(result["production_path"], "ROUTE-LASER-EDGE-PACK")
        self.assertEqual(repository.created[0].stage_type, "LASER")


if __name__ == "__main__":
    unittest.main()
