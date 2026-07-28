from __future__ import annotations

from typing import Any, Sequence

import frappe
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from almdina_erp.almdina_erp.application.shop_floor.commands import (
    OrderState,
    ShopFloorCommandPort,
    StageState,
)
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_gateway


class FrappeShopFloorCommandRepository(ShopFloorCommandPort):
    """Frappe persistence adapter for shop-floor write use cases."""

    @staticmethod
    def _stage_state(stage: Any) -> StageState:
        return StageState(
            name=str(stage.name),
            order_name=str(stage.door_cutting_order),
            stage_type=str(stage.stage_type),
            status=str(stage.status),
            assigned_to=stage.assigned_to or None,
            sequence=cint(stage.sequence),
            start_time=stage.start_time or None,
            paused_seconds=cint(stage.paused_seconds),
            piece_label=stage.piece_label or None,
        )

    def current_user(self) -> str:
        return str(frappe.session.user)

    def require_dispatch_permission(self) -> None:
        shop_floor_gateway.require_roles(*shop_floor_gateway.DISPATCH_ROLES)

    def require_delivery_permission(self) -> None:
        shop_floor_gateway.require_roles(*shop_floor_gateway.ADMIN_ROLES)

    def require_revert_permission(self) -> None:
        shop_floor_gateway.require_roles(*shop_floor_gateway.ADMIN_ROLES)

    def require_stage_access(self, stage_name: str) -> None:
        stage = shop_floor_gateway.get_stage(stage_name)
        shop_floor_gateway.require_stage_assignee_or_admin(stage)

    def get_order_state(self, order_name: str) -> OrderState:
        order = shop_floor_gateway.get_order(order_name)
        return OrderState(
            name=str(order.name),
            status=str(order.status or ""),
            production_path=order.production_path or None,
            current_stage=order.current_production_stage or None,
            has_cutting_plan=bool(order.cutting_plan_json),
            plan_needs_recalculation=bool(cint(order.plan_needs_recalculation)),
            drawing_dxf_status=order.drawing_dxf_status or None,
        )

    def get_stage_state(self, stage_name: str) -> StageState:
        return self._stage_state(shop_floor_gateway.get_stage(stage_name))

    def validate_special_shapes(self, order_name: str) -> None:
        shop_floor_gateway.get_order(order_name).ensure_special_shapes_documented()

    def assert_worker_for_stage(self, user: str, stage_type: str) -> None:
        shop_floor_gateway.assert_enabled_user_has_stage_role(user, stage_type)

    def get_users_for_stage(self, stage_type: str) -> list[dict[str, str]]:
        return shop_floor_gateway.get_users_for_stage(stage_type)

    def cancel_non_shop_floor_active_stages(self, order_name: str) -> None:
        shop_floor_gateway.cancel_non_shop_floor_active_stages(order_name)

    def create_stage(
        self,
        *,
        order_name: str,
        stage_type: str,
        assignee: str,
        sequence: int,
    ) -> StageState:
        stage = shop_floor_gateway.create_stage(
            order_name,
            stage_type,
            assignee,
            sequence,
        )
        return self._stage_state(stage)

    def track_order_to_stage(
        self,
        order_name: str,
        *,
        stage_name: str,
        path: str | None = None,
    ) -> None:
        stage = shop_floor_gateway.get_stage(stage_name)
        shop_floor_gateway.set_order_tracking(order_name, path=path, stage=stage)

    def track_order_ready_for_delivery(self, order_name: str) -> None:
        shop_floor_gateway.set_order_tracking(
            order_name,
            status="Ready for Delivery",
            department="جاهز للتسليم",
            assignee="",
            department_status="مكتمل",
            clear_stage=True,
        )

    def track_order_delivered(self, order_name: str) -> None:
        shop_floor_gateway.set_order_tracking(
            order_name,
            status="Delivered",
            department="تم التسليم",
            assignee="",
            department_status="مكتمل",
            clear_stage=True,
        )

    def log_stage_event(
        self,
        stage_name: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        shop_floor_gateway.log_event(
            shop_floor_gateway.get_stage(stage_name),
            event_type,
            details,
        )

    def consume_stock_if_due(
        self,
        order_name: str,
        stage_type: str,
        trigger: str,
    ) -> None:
        shop_floor_gateway.maybe_consume_stock(order_name, stage_type, trigger)

    def register_remnants_if_due(
        self,
        order_name: str,
        stage_type: str,
    ) -> dict[str, Any] | None:
        return shop_floor_gateway.maybe_register_remnants(order_name, stage_type)

    def close_open_pause(self, stage_name: str, resumed_by: str) -> None:
        stage = shop_floor_gateway.get_stage(stage_name)
        shop_floor_gateway.close_open_pause(stage, resumed_by)
        stage.save(ignore_permissions=True)

    def start_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
    ) -> StageState:
        stage = shop_floor_gateway.get_stage(stage_name)
        stage.started_by = actor
        stage.start_time = now_datetime()
        stage.status = target_status
        if not stage.assigned_to:
            stage.assigned_to = actor
        stage.save(ignore_permissions=True)
        return self._stage_state(stage)

    def complete_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
        completed_qty: int,
    ) -> StageState:
        stage = shop_floor_gateway.get_stage(stage_name)
        finish_time = now_datetime()
        stage.finish_time = finish_time
        stage.finished_by = actor
        stage.status = target_status
        stage.completed_qty = completed_qty
        if stage.start_time:
            total_seconds = max(
                0,
                cint(time_diff_in_seconds(finish_time, stage.start_time)),
            )
            stage.actual_working_seconds = max(
                0,
                total_seconds - cint(stage.paused_seconds),
            )
        stage.save(ignore_permissions=True)
        return self._stage_state(stage)

    def required_piece_qty(self, order_name: str) -> int:
        return shop_floor_gateway.required_piece_qty(order_name)

    def get_order_status(self, order_name: str) -> str | None:
        return shop_floor_gateway.get_order_status(order_name)

    def list_revert_candidates(
        self,
        order_name: str,
        stage_type: str,
    ) -> Sequence[StageState]:
        return [
            self._stage_state(shop_floor_gateway.get_stage(row.name))
            for row in shop_floor_gateway.get_revert_stage_candidates(
                order_name,
                stage_type,
            )
        ]

    def stage_exists(self, stage_name: str | None) -> bool:
        return shop_floor_gateway.stage_exists(stage_name)

    def list_later_stages(
        self,
        order_name: str,
        sequence: int,
    ) -> Sequence[StageState]:
        return [
            self._stage_state(shop_floor_gateway.get_stage(row.name))
            for row in shop_floor_gateway.get_later_stages(order_name, sequence)
        ]

    def cancel_stage(self, stage_name: str, *, target_status: str) -> StageState:
        stage = shop_floor_gateway.get_stage(stage_name)
        stage.status = target_status
        stage.save(ignore_permissions=True)
        return self._stage_state(stage)

    def reopen_stage(self, stage_name: str, *, target_status: str) -> StageState:
        stage = shop_floor_gateway.get_stage(stage_name)
        stage.status = target_status
        stage.started_by = None
        stage.start_time = None
        stage.finished_by = None
        stage.finish_time = None
        stage.actual_working_seconds = 0
        stage.paused_seconds = 0
        stage.completed_qty = 0
        stage.pauses = []
        stage.save(ignore_permissions=True)
        return self._stage_state(stage)


__all__ = ["FrappeShopFloorCommandRepository"]
