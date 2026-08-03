from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.shop_floor.queries import (
    SHOP_FLOOR_DETAIL_CAPABILITIES,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_STAGE_TYPES,
    department_for_stage_type,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_authorization
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    document_has_capability,
    granted_capabilities,
)


_SUPERVISOR_CAPABILITIES = (
    Capability.REASSIGN_WORKER,
    Capability.REVERT_DEPARTMENT,
    Capability.MARK_DELIVERED,
)


class FrappeShopFloorQueryRepository:
    """Frappe read adapter for shop-floor application queries."""

    def current_user(self) -> str:
        return frappe.session.user

    def session_identity(self) -> dict[str, Any]:
        user = self.current_user()
        full_name = frappe.get_cached_value("User", user, "full_name") or user
        roles = set(frappe.get_roles(user))
        departments = [
            department_for_stage_type(stage_type) or stage_type
            for stage_type, role in shop_floor_authorization.STAGE_ROLE_BY_TYPE.items()
            if role in roles or user == "Administrator"
        ]
        return {
            "user": user,
            "full_name": full_name,
            "departments": departments,
        }

    def global_capabilities(self) -> frozenset[str]:
        return granted_capabilities(user=self.current_user())

    def is_admin(self) -> bool:
        return any(
            doctype_has_capability(capability)
            for capability in _SUPERVISOR_CAPABILITIES
        )

    def capabilities_for_order(self, order: Any) -> frozenset[str]:
        return frozenset(
            capability
            for capability in SHOP_FLOOR_DETAIL_CAPABILITIES
            if document_has_capability(order, capability)
        )

    def list_inbox_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        filters: dict[str, Any] = {
            "status": ["in", ["Pending", "In Progress", "Paused"]],
            "stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
        }
        if not is_admin:
            filters["assigned_to"] = user
        return frappe.get_all(
            "Production Stage",
            filters=filters,
            fields=[
                "name",
                "door_cutting_order",
                "stage_type",
                "status",
                "assigned_to",
                "sequence",
                "modified",
            ],
            order_by="modified desc",
        )

    def list_archive_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        filters: dict[str, Any] = {
            "status": "Completed",
            "stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
        }
        if not is_admin:
            filters["assigned_to"] = user
        return frappe.get_all(
            "Production Stage",
            filters=filters,
            fields=[
                "name",
                "door_cutting_order",
                "stage_type",
                "status",
                "assigned_to",
                "sequence",
                "finish_time",
                "modified",
            ],
            order_by="modified desc",
            limit_page_length=100,
        )

    def current_stage_names(
        self,
        order_names: Sequence[str],
    ) -> dict[str, str | None]:
        if not order_names:
            return {}
        return {
            row.name: row.current_production_stage
            for row in frappe.get_all(
                "Door Cutting Order",
                filters={"name": ["in", list(order_names)]},
                fields=["name", "current_production_stage"],
            )
        }

    def order_summaries(self, order_names: Sequence[str]) -> dict[str, Any]:
        if not order_names:
            return {}
        return {
            row.name: row
            for row in frappe.get_all(
                "Door Cutting Order",
                filters={"name": ["in", list(order_names)]},
                fields=[
                    "name",
                    "customer",
                    "order_date",
                    "board_description",
                    "edge_color",
                    "status",
                    "production_path",
                    "current_department",
                    "department_status",
                    "current_production_stage",
                    "approved_plan",
                    "production_dxf",
                    "drawing_dxf_status",
                    "revision",
                ],
            )
        }

    def get_order(self, order_name: str) -> Any:
        return frappe.get_doc("Door Cutting Order", order_name)

    def can_view_order(self, order: Any) -> bool:
        if self.is_admin() or frappe.has_permission(order, "read"):
            return True
        return bool(
            frappe.db.exists(
                "Production Stage",
                {
                    "door_cutting_order": order.name,
                    "assigned_to": self.current_user(),
                    "stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
                },
            )
        )

    def list_order_stages(self, order_name: str) -> list[Any]:
        return frappe.get_all(
            "Production Stage",
            filters={
                "door_cutting_order": order_name,
                "stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
            },
            fields=[
                "name",
                "stage_type",
                "status",
                "assigned_to",
                "sequence",
                "start_time",
                "finish_time",
                "piece_label",
            ],
            order_by="sequence asc",
        )

    def get_stage_summary(self, stage_name: str) -> Any | None:
        return frappe.db.get_value(
            "Production Stage",
            stage_name,
            ["name", "status", "stage_type", "assigned_to"],
            as_dict=True,
        )

    def load_plan_snapshot(
        self,
        order: Any,
        plan_source: str | None = None,
    ) -> dict[str, Any]:
        if plan_source == "System":
            from almdina_erp.almdina_erp.services.dual_plan_fields import (
                get_system_plan_json,
            )

            raw = getattr(order, "system_plan_json", None) or get_system_plan_json(order)
            return self._parse_snapshot(raw)

        if plan_source == "Custom":
            from almdina_erp.almdina_erp.services.dual_plan_fields import (
                get_custom_plan_json,
            )

            raw = getattr(order, "custom_plan_json", None) or get_custom_plan_json(order)
            return self._parse_snapshot(raw)

        snapshot: dict[str, Any] = {}
        approved_plan = getattr(order, "approved_plan", None)
        if approved_plan:
            snapshot = self._parse_snapshot(
                frappe.db.get_value("Cutting Plan", approved_plan, "snapshot_json")
            )
        if not snapshot:
            snapshot = self._parse_snapshot(
                getattr(order, "cutting_plan_json", None)
            )
        return snapshot

    def user_can_view_dual_plans(self) -> bool:
        return any(
            doctype_has_capability(capability)
            for capability in (
                Capability.VIEW_DRAWING_WORKSPACE,
                Capability.APPROVE_DXF,
            )
        )

    def get_order_status(self, order_name: str) -> str | None:
        return frappe.db.get_value("Door Cutting Order", order_name, "status")

    def list_revert_stages(self, order_name: str) -> list[Any]:
        return frappe.get_all(
            "Production Stage",
            filters={
                "door_cutting_order": order_name,
                "stage_type": ["in", list(SHOP_FLOOR_STAGE_TYPES)],
                "status": ["in", ["Completed", "In Progress", "Paused", "Pending"]],
            },
            fields=[
                "name",
                "stage_type",
                "status",
                "sequence",
                "assigned_to",
                "piece_label",
            ],
            order_by="sequence asc",
        )

    def get_users_for_stage(self, stage_type: str) -> list[dict[str, str]]:
        return shop_floor_authorization.get_users_for_stage(stage_type)

    @staticmethod
    def _parse_snapshot(raw: Any) -> dict[str, Any]:
        if not raw:
            return {}
        parsed = frappe.parse_json(raw) or {}
        return parsed if isinstance(parsed, dict) else {}
