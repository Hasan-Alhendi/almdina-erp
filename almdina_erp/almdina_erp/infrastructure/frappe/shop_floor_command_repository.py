from __future__ import annotations

from typing import Any, Sequence

from almdina_erp.almdina_erp.application.shop_floor.commands import (
    OrderState,
    ShopFloorCommandPort,
    StageState,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    PRODUCTION_ACTIONS,
)
from almdina_erp.almdina_erp.infrastructure.frappe import (
    order_tracking_repository,
    production_event_repository,
    production_routing_repository,
    production_stage_repository,
    shop_floor_authorization,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class FrappeShopFloorCommandRepository(ShopFloorCommandPort):
    """Composes focused Frappe adapters for shop-floor write use cases."""

    @staticmethod
    def _stage_state(stage: Any) -> StageState:
        return StageState(
            name=str(stage.name),
            order_name=str(stage.door_cutting_order),
            stage_type=str(stage.stage_type),
            status=str(stage.status),
            assigned_to=stage.assigned_to or None,
            sequence=_as_int(stage.sequence),
            department_label=getattr(stage, "department_label", None) or None,
            operational_role=getattr(stage, "operational_role", None) or None,
            start_time=stage.start_time or None,
            paused_seconds=_as_int(stage.paused_seconds),
            piece_label=stage.piece_label or None,
        )

    def current_user(self) -> str:
        return shop_floor_authorization.current_user()

    def capabilities_for_order(self, order_name: str) -> frozenset[str]:
        order = order_tracking_repository.get_order(order_name)
        return frozenset(
            capability
            for capability in PRODUCTION_ACTIONS
            if document_has_capability(order, capability)
        )

    def lock_order(self, order_name: str) -> None:
        order_tracking_repository.lock_order(order_name)

    def lock_stage(self, stage_name: str) -> None:
        production_stage_repository.lock_stage(stage_name)

    def get_order_state(self, order_name: str) -> OrderState:
        order = order_tracking_repository.get_order(order_name)
        return OrderState(
            name=str(order.name),
            status=str(order.status or ""),
            production_path=order.production_path or None,
            current_stage=order.current_production_stage or None,
            has_cutting_plan=bool(order.cutting_plan_json),
            plan_needs_recalculation=bool(_as_int(order.plan_needs_recalculation)),
            drawing_dxf_status=order.drawing_dxf_status or None,
        )

    def get_stage_state(self, stage_name: str) -> StageState:
        return self._stage_state(production_stage_repository.get_stage(stage_name))

    def validate_special_shapes(self, order_name: str) -> None:
        order_tracking_repository.get_order(order_name).ensure_special_shapes_documented()

    def get_production_route(self, route_name: str):
        return production_routing_repository.get_route(route_name)

    def assert_worker_for_role(self, user: str, role: str) -> None:
        shop_floor_authorization.assert_enabled_user_has_role(user, role)

    def get_users_for_role(self, role: str) -> list[dict[str, str]]:
        return shop_floor_authorization.get_users_for_role(role)

    def cancel_active_order_stages(self, order_name: str) -> None:
        production_stage_repository.cancel_active_order_stages(order_name)

    def create_stage(
        self,
        *,
        order_name: str,
        stage_type: str,
        assignee: str,
        sequence: int,
        department_label: str | None = None,
        operational_role: str | None = None,
    ) -> StageState:
        stage = production_stage_repository.create_stage(
            order_name,
            stage_type,
            assignee,
            sequence,
            department_label=department_label,
            operational_role=operational_role,
        )
        return self._stage_state(stage)

    def reassign_stage(self, stage_name: str, *, assignee: str) -> StageState:
        return self._stage_state(
            production_stage_repository.reassign_stage(
                stage_name,
                assignee=assignee,
            )
        )

    def track_order_to_stage(
        self,
        order_name: str,
        *,
        stage_name: str,
        path: str | None = None,
    ) -> None:
        stage = production_stage_repository.get_stage(stage_name)
        order_tracking_repository.set_order_tracking(order_name, path=path, stage=stage)

    def track_order_ready_for_delivery(self, order_name: str) -> None:
        order_tracking_repository.set_order_tracking(
            order_name,
            status="Ready for Delivery",
            department="جاهز للتسليم",
            assignee="",
            department_status="مكتمل",
            clear_stage=True,
        )

    def track_order_delivered(self, order_name: str) -> None:
        order_tracking_repository.set_order_tracking(
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
        production_event_repository.log_event(
            production_stage_repository.get_stage(stage_name),
            event_type,
            details,
        )

    def close_open_pause(self, stage_name: str, resumed_by: str) -> None:
        production_stage_repository.close_open_pause(stage_name, resumed_by)

    def start_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
    ) -> StageState:
        return self._stage_state(
            production_stage_repository.start_stage(
                stage_name,
                actor=actor,
                target_status=target_status,
            )
        )

    def complete_stage(
        self,
        stage_name: str,
        *,
        actor: str,
        target_status: str,
        completed_qty: int,
    ) -> StageState:
        return self._stage_state(
            production_stage_repository.complete_stage(
                stage_name,
                actor=actor,
                target_status=target_status,
                completed_qty=completed_qty,
            )
        )

    def required_piece_qty(self, order_name: str) -> int:
        return order_tracking_repository.required_piece_qty(order_name)

    def get_order_status(self, order_name: str) -> str | None:
        return order_tracking_repository.get_order_status(order_name)

    def list_revert_candidates(
        self,
        order_name: str,
        stage_type: str,
    ) -> Sequence[StageState]:
        return [
            self._stage_state(production_stage_repository.get_stage(row.name))
            for row in production_stage_repository.list_revert_stage_candidates(
                order_name,
                stage_type,
            )
        ]

    def stage_exists(self, stage_name: str | None) -> bool:
        return production_stage_repository.stage_exists(stage_name)

    def list_later_stages(
        self,
        order_name: str,
        sequence: int,
    ) -> Sequence[StageState]:
        return [
            self._stage_state(production_stage_repository.get_stage(row.name))
            for row in production_stage_repository.list_later_stages(order_name, sequence)
        ]

    def cancel_stage(self, stage_name: str, *, target_status: str) -> StageState:
        return self._stage_state(
            production_stage_repository.cancel_stage(
                stage_name,
                target_status=target_status,
            )
        )

    def reopen_stage(self, stage_name: str, *, target_status: str) -> StageState:
        return self._stage_state(
            production_stage_repository.reopen_stage(
                stage_name,
                target_status=target_status,
            )
        )


__all__ = ["FrappeShopFloorCommandRepository"]
