from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import production_routing_repository
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_authorization import (
    assert_enabled_user_has_role,
    get_users_for_role,
)


_ORDER_DOCTYPE = "Door Cutting Order"


class FrappeOrderIntakeRepository:
    """Frappe adapter for the pre-production intake lifecycle."""

    def current_user(self) -> str:
        return str(frappe.session.user or "")

    def is_admin(self) -> bool:
        return self.current_user() == "Administrator"

    def can_edit_order(self, order: Any) -> bool:
        return document_has_capability(order, Capability.EDIT_ORDER)

    def get_order(self, order_name: str, *, for_update: bool = False) -> Any:
        resolved = str(order_name or "").strip()
        if not resolved:
            frappe.throw("حدد الطلب أولًا.")
        if for_update:
            rows = frappe.db.sql(
                "select name from `tabDoor Cutting Order` where name = %s for update",
                (resolved,),
                as_dict=True,
            )
            if not rows:
                frappe.throw(f"الطلب {resolved} غير موجود.")
        return frappe.get_doc(_ORDER_DOCTYPE, resolved)

    def list_orders_without_intake_stage(self) -> list[dict[str, Any]]:
        """Return migration candidates; application/domain decide final eligibility."""

        return frappe.db.sql(
            """
            select
                name,
                owner,
                workflow_stage,
                production_path,
                current_production_stage,
                current_assignee
            from `tabDoor Cutting Order`
            where coalesce(workflow_stage, '') = ''
            order by creation asc, name asc
            """,
            as_dict=True,
        )

    def get_route(self, route_name: str):
        return production_routing_repository.get_route(route_name)

    def list_active_routes(self):
        return production_routing_repository.list_active_routes()

    def assert_assignee_qualified(self, user: str, operational_role: str) -> None:
        assert_enabled_user_has_role(user, operational_role)

    def list_workers_for_role(self, operational_role: str) -> list[dict[str, str]]:
        return get_users_for_role(operational_role)

    def initialize_data_entry(
        self,
        order: Any,
        *,
        assignee: str,
        workflow_stage: str,
    ) -> None:
        values = {
            "workflow_stage": workflow_stage,
            "current_assignee": assignee,
        }
        frappe.db.set_value(
            _ORDER_DOCTYPE,
            order.name,
            values,
            update_modified=False,
        )
        if isinstance(order, dict):
            order.update(values)
        else:
            for fieldname, value in values.items():
                setattr(order, fieldname, value)

    def save_pending_dispatch_plan(
        self,
        order: Any,
        *,
        route_name: str,
        assignee: str,
        workflow_stage: str,
        planned_by: str,
    ) -> None:
        values = {
            "workflow_stage": workflow_stage,
            "planned_production_route": route_name,
            "planned_first_assignee": assignee,
            "dispatch_planned_at": now_datetime(),
            "dispatch_planned_by": planned_by,
        }
        frappe.db.set_value(
            _ORDER_DOCTYPE,
            order.name,
            values,
            update_modified=True,
        )
        for fieldname, value in values.items():
            setattr(order, fieldname, value)


__all__ = ["FrappeOrderIntakeRepository"]
