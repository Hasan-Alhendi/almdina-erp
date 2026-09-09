from __future__ import annotations

from types import SimpleNamespace
import unittest

from almdina_erp.almdina_erp.application.orders.intake_planning import (
    backfill_data_entry,
    finish_data_entry,
    get_finish_data_entry_options,
    initialize_data_entry,
)
from almdina_erp.almdina_erp.domain.orders.intake_lifecycle import (
    DATA_ENTRY,
    READY_TO_DISPATCH,
    IntakePermissionError,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)


def _route() -> ProductionRoute:
    return ProductionRoute(
        name="ROUTE-A",
        label="مسار A",
        stages=(
            RoutingStage(
                sequence=10,
                stage_type="DRAWING",
                department_label="رسم",
                operational_role="Drawing Operator",
            ),
            RoutingStage(
                sequence=20,
                stage_type="CNC",
                department_label="CNC",
                operational_role="CNC Operator",
            ),
        ),
    )


class FakeIntakeRepository:
    def __init__(self) -> None:
        self.actor = "entry@example.com"
        self.admin = False
        self.order = SimpleNamespace(
            name="DCO-1",
            owner=self.actor,
            workflow_stage="",
            production_path="",
            current_production_stage="",
            current_assignee="",
            planned_production_route="",
            planned_first_assignee="",
        )
        self.route = _route()
        self.initializations = 0
        self.saved_plans = 0

    def current_user(self) -> str:
        return self.actor

    def is_admin(self) -> bool:
        return self.admin

    def can_edit_order(self, order) -> bool:
        return True

    def get_order(self, order_name: str, *, for_update: bool = False):
        assert order_name == self.order.name
        return self.order

    def list_orders_without_intake_stage(self):
        return [self.order] if not self.order.workflow_stage else []

    def get_route(self, route_name: str) -> ProductionRoute:
        if route_name != self.route.name:
            raise ValueError("invalid route")
        return self.route

    def list_active_routes(self):
        return [self.route]

    def assert_assignee_qualified(self, user: str, operational_role: str) -> None:
        if user != "drawing@example.com" or operational_role != "Drawing Operator":
            raise ValueError("worker role mismatch")

    def list_workers_for_role(self, operational_role: str):
        if operational_role != "Drawing Operator":
            return []
        return [{"name": "drawing@example.com", "full_name": "Drawing Worker"}]

    def initialize_data_entry(
        self,
        order,
        *,
        assignee: str,
        workflow_stage: str,
    ) -> None:
        self.initializations += 1
        order.workflow_stage = workflow_stage
        order.current_assignee = assignee

    def save_pending_dispatch_plan(
        self,
        order,
        *,
        route_name: str,
        assignee: str,
        workflow_stage: str,
        planned_by: str,
    ) -> None:
        self.saved_plans += 1
        order.workflow_stage = workflow_stage
        order.planned_production_route = route_name
        order.planned_first_assignee = assignee
        order.dispatch_planned_by = planned_by


class IntakePlanningTests(unittest.TestCase):
    def test_first_persisted_save_initializes_data_entry_once(self) -> None:
        repository = FakeIntakeRepository()

        self.assertTrue(initialize_data_entry(repository, repository.order))
        self.assertFalse(initialize_data_entry(repository, repository.order))

        self.assertEqual(repository.initializations, 1)
        self.assertEqual(repository.order.workflow_stage, DATA_ENTRY)
        self.assertEqual(repository.order.current_assignee, repository.order.owner)

    def test_migrate_backfill_is_idempotent_for_legacy_never_dispatched_order(self) -> None:
        repository = FakeIntakeRepository()

        self.assertEqual(backfill_data_entry(repository), 1)
        self.assertEqual(backfill_data_entry(repository), 0)

        self.assertEqual(repository.initializations, 1)
        self.assertEqual(repository.order.workflow_stage, DATA_ENTRY)
        self.assertEqual(repository.order.current_assignee, repository.order.owner)

    def test_migrate_backfill_does_not_reopen_order_that_entered_production(self) -> None:
        repository = FakeIntakeRepository()
        repository.order.production_path = "ROUTE-A"
        repository.order.current_production_stage = "STAGE-1"

        self.assertEqual(backfill_data_entry(repository), 0)
        self.assertEqual(repository.initializations, 0)
        self.assertEqual(repository.order.workflow_stage, "")

    def test_finish_data_entry_stores_plan_without_starting_production(self) -> None:
        repository = FakeIntakeRepository()
        initialize_data_entry(repository, repository.order)

        result = finish_data_entry(
            repository,
            repository.order.name,
            repository.route.name,
            "drawing@example.com",
        )

        self.assertEqual(result["workflow_stage"], READY_TO_DISPATCH)
        self.assertEqual(repository.order.workflow_stage, READY_TO_DISPATCH)
        self.assertEqual(repository.order.planned_production_route, "ROUTE-A")
        self.assertEqual(repository.order.planned_first_assignee, "drawing@example.com")
        self.assertEqual(repository.order.current_assignee, repository.order.owner)
        self.assertEqual(repository.order.production_path, "")
        self.assertEqual(repository.order.current_production_stage, "")
        self.assertEqual(repository.saved_plans, 1)

    def test_ready_to_dispatch_plan_can_be_updated_idempotently(self) -> None:
        repository = FakeIntakeRepository()
        initialize_data_entry(repository, repository.order)

        for _ in range(2):
            finish_data_entry(
                repository,
                repository.order.name,
                repository.route.name,
                "drawing@example.com",
            )

        self.assertEqual(repository.order.workflow_stage, READY_TO_DISPATCH)
        self.assertEqual(repository.saved_plans, 2)
        self.assertEqual(repository.order.production_path, "")
        self.assertEqual(repository.order.current_production_stage, "")

    def test_non_owner_cannot_plan_dispatch(self) -> None:
        repository = FakeIntakeRepository()
        initialize_data_entry(repository, repository.order)
        repository.actor = "other@example.com"

        with self.assertRaises(IntakePermissionError):
            finish_data_entry(
                repository,
                repository.order.name,
                repository.route.name,
                "drawing@example.com",
            )

    def test_options_use_first_stage_role_and_existing_pending_plan(self) -> None:
        repository = FakeIntakeRepository()
        initialize_data_entry(repository, repository.order)
        repository.order.planned_production_route = repository.route.name
        repository.order.planned_first_assignee = "drawing@example.com"

        payload = get_finish_data_entry_options(repository, repository.order.name)

        self.assertEqual(payload["default_route"], "ROUTE-A")
        self.assertEqual(payload["planned_first_assignee"], "drawing@example.com")
        self.assertEqual(payload["routes"][0]["stages"][0]["department"], "رسم")
        self.assertEqual(
            payload["workers"]["ROUTE-A"][0]["name"],
            "drawing@example.com",
        )


if __name__ == "__main__":
    unittest.main()
