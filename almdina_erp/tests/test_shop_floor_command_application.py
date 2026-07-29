from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime
from typing import Any, Sequence

from almdina_erp.almdina_erp.application.shop_floor import commands


class FakeShopFloorCommandRepository:
    def __init__(self) -> None:
        self.actor = "worker@example.com"
        self.orders: dict[str, commands.OrderState] = {}
        self.stages: dict[str, commands.StageState] = {}
        self.users: dict[str, list[dict[str, str]]] = {}
        self.calls: list[tuple[Any, ...]] = []
        self._counter = 0

    def current_user(self) -> str:
        return self.actor

    def require_dispatch_permission(self) -> None:
        self.calls.append(("require_dispatch_permission",))

    def require_delivery_permission(self) -> None:
        self.calls.append(("require_delivery_permission",))

    def require_revert_permission(self) -> None:
        self.calls.append(("require_revert_permission",))

    def require_stage_access(self, stage_name: str) -> None:
        self.calls.append(("require_stage_access", stage_name))

    def get_order_state(self, order_name: str) -> commands.OrderState:
        return self.orders[order_name]

    def get_stage_state(self, stage_name: str) -> commands.StageState:
        return self.stages[stage_name]

    def validate_special_shapes(self, order_name: str) -> None:
        self.calls.append(("validate_special_shapes", order_name))

    def assert_worker_for_stage(self, user: str, stage_type: str) -> None:
        self.calls.append(("assert_worker_for_stage", user, stage_type))

    def get_users_for_stage(self, stage_type: str) -> list[dict[str, str]]:
        return list(self.users.get(stage_type, []))

    def cancel_non_shop_floor_active_stages(self, order_name: str) -> None:
        self.calls.append(("cancel_non_shop_floor_active_stages", order_name))

    def create_stage(
        self,
        *,
        order_name: str,
        stage_type: str,
        assignee: str,
        sequence: int,
    ) -> commands.StageState:
        self._counter += 1
        stage = commands.StageState(
            name=f"PST-{self._counter}",
            order_name=order_name,
            stage_type=stage_type,
            status="Pending",
            assigned_to=assignee,
            sequence=sequence,
        )
        self.stages[stage.name] = stage
        self.calls.append(("create_stage", order_name, stage_type, assignee, sequence))
        return stage

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
            self.orders[order_name],
            status="Ready for Delivery",
            current_stage=None,
        )
        self.calls.append(("track_order_ready_for_delivery", order_name))

    def track_order_delivered(self, order_name: str) -> None:
        self.orders[order_name] = replace(
            self.orders[order_name],
            status="Delivered",
            current_stage=None,
        )
        self.calls.append(("track_order_delivered", order_name))

    def log_stage_event(
        self,
        stage_name: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append(("log_stage_event", stage_name, event_type, details or {}))

    def consume_stock_if_due(
        self,
        order_name: str,
        stage_type: str,
        trigger: str,
    ) -> None:
        self.calls.append(("consume_stock_if_due", order_name, stage_type, trigger))

    def register_remnants_if_due(
        self,
        order_name: str,
        stage_type: str,
    ) -> dict[str, Any] | None:
        self.calls.append(("register_remnants_if_due", order_name, stage_type))
        return {"registered": True}

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
        self.calls.append(
            ("complete_stage", stage_name, actor, target_status, completed_qty)
        )
        return updated

    def required_piece_qty(self, order_name: str) -> int:
        return 7

    def get_order_status(self, order_name: str) -> str | None:
        return self.orders[order_name].status

    def list_revert_candidates(
        self,
        order_name: str,
        stage_type: str,
    ) -> Sequence[commands.StageState]:
        return [
            stage
            for stage in self.stages.values()
            if stage.order_name == order_name and stage.stage_type == stage_type
        ]

    def stage_exists(self, stage_name: str | None) -> bool:
        return bool(stage_name and stage_name in self.stages)

    def list_later_stages(
        self,
        order_name: str,
        sequence: int,
    ) -> Sequence[commands.StageState]:
        return sorted(
            (
                stage
                for stage in self.stages.values()
                if stage.order_name == order_name and stage.sequence > sequence
            ),
            key=lambda stage: stage.sequence,
        )

    def cancel_stage(
        self,
        stage_name: str,
        *,
        target_status: str,
    ) -> commands.StageState:
        updated = replace(self.stages[stage_name], status=target_status)
        self.stages[stage_name] = updated
        self.calls.append(("cancel_stage", stage_name, target_status))
        return updated

    def reopen_stage(
        self,
        stage_name: str,
        *,
        target_status: str,
    ) -> commands.StageState:
        updated = replace(self.stages[stage_name], status=target_status)
        self.stages[stage_name] = updated
        self.calls.append(("reopen_stage", stage_name, target_status))
        return updated


class TestShopFloorCommandApplication(unittest.TestCase):
    def _approved_order(self, name: str = "DCO-1") -> commands.OrderState:
        return commands.OrderState(
            name=name,
            status="Approved",
            production_path=None,
            current_stage=None,
            has_cutting_plan=True,
            plan_needs_recalculation=False,
        )

    def test_dispatch_orchestrates_domain_and_port_without_frappe(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = self._approved_order()

        result = commands.dispatch_order(
            repository,
            "DCO-1",
            "Drawing",
            "drawing@example.com",
        )

        self.assertEqual(result["status"], "At Drawing")
        self.assertEqual(result["stage"], "PST-1")
        self.assertIn(("validate_special_shapes", "DCO-1"), repository.calls)
        self.assertIn(
            ("assert_worker_for_stage", "drawing@example.com", "Drawing"),
            repository.calls,
        )
        self.assertEqual(repository.orders["DCO-1"].current_stage, "PST-1")

    def test_start_stage_updates_tracking_without_inventory_side_effects(self) -> None:
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
            assigned_to="worker@example.com",
            sequence=10,
        )

        result = commands.start_my_stage(repository, "PST-1")

        self.assertEqual(result["status"], "In Progress")
        self.assertIn(
            ("start_stage", "PST-1", "worker@example.com", "In Progress"),
            repository.calls,
        )
        self.assertFalse(
            any(call[0] in {"consume_stock_if_due", "register_remnants_if_due"} for call in repository.calls)
        )

    def test_drawing_handoff_requires_approved_dxf(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At Drawing",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
            drawing_dxf_status="Uploaded",
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="Drawing",
            status="In Progress",
            assigned_to="worker@example.com",
            sequence=10,
        )

        with self.assertRaisesRegex(
            commands.ShopFloorCommandError,
            "Approve the production DXF",
        ):
            commands.handoff_to_next(
                repository,
                "PST-1",
                "cnc@example.com",
            )

    def test_final_handoff_marks_order_ready_for_delivery(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At Sanding",
            production_path="Drawing",
            current_stage="PST-1",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
        )
        repository.stages["PST-1"] = commands.StageState(
            name="PST-1",
            order_name="DCO-1",
            stage_type="Sanding",
            status="In Progress",
            assigned_to="worker@example.com",
            sequence=30,
        )

        result = commands.handoff_to_next(repository, "PST-1")

        self.assertTrue(result["ready_for_delivery"])
        self.assertEqual(repository.orders["DCO-1"].status, "Ready for Delivery")
        self.assertIn(
            ("track_order_ready_for_delivery", "DCO-1"),
            repository.calls,
        )

    def test_revert_cancels_later_stages_and_reopens_target(self) -> None:
        repository = FakeShopFloorCommandRepository()
        repository.orders["DCO-1"] = commands.OrderState(
            name="DCO-1",
            status="At Sanding",
            production_path="Drawing",
            current_stage="PST-3",
            has_cutting_plan=True,
            plan_needs_recalculation=False,
        )
        repository.stages.update(
            {
                "PST-1": commands.StageState(
                    name="PST-1",
                    order_name="DCO-1",
                    stage_type="Drawing",
                    status="Completed",
                    assigned_to="drawing@example.com",
                    sequence=10,
                ),
                "PST-2": commands.StageState(
                    name="PST-2",
                    order_name="DCO-1",
                    stage_type="CNC",
                    status="Completed",
                    assigned_to="cnc@example.com",
                    sequence=20,
                ),
                "PST-3": commands.StageState(
                    name="PST-3",
                    order_name="DCO-1",
                    stage_type="Sanding",
                    status="Pending",
                    assigned_to="sanding@example.com",
                    sequence=30,
                ),
            }
        )

        result = commands.revert_department(
            repository,
            "DCO-1",
            target_stage_type="Drawing",
        )

        self.assertEqual(result["stage"], "PST-1")
        self.assertEqual(repository.stages["PST-1"].status, "Pending")
        self.assertEqual(repository.stages["PST-2"].status, "Cancelled")
        self.assertEqual(repository.stages["PST-3"].status, "Cancelled")
        self.assertEqual(repository.orders["DCO-1"].current_stage, "PST-1")


if __name__ == "__main__":
    unittest.main()
