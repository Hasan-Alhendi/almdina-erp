from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import frappe

from almdina_erp import permissions
from almdina_erp.almdina_erp.application.shop_floor.queries import (
    SHOP_FLOOR_DETAIL_CAPABILITIES,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import SYSTEM, UPLOADED_DXF
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_authorization
from almdina_erp.almdina_erp.infrastructure.frappe import (
    production_routing_repository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    document_has_capability,
    granted_capabilities,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    current_working_plan,
    latest_plan,
    production_plan_facts,
)


_ORDER_DOCTYPE = "Door Cutting Order"
_ORDER_DOCUMENT_CACHE_KEY = "almdina_shop_floor_order_documents"
_SUPERVISOR_CAPABILITIES = (
    Capability.REASSIGN_WORKER,
    Capability.REVERT_DEPARTMENT,
    Capability.MARK_DELIVERED,
)


def _order_name(order: Any) -> str:
    if isinstance(order, dict):
        return str(order.get("name") or "").strip()
    return str(getattr(order, "name", "") or "").strip()


def _order_document(order: Any) -> Any | None:
    """Resolve list projections to the real transactional document.

    Shop-floor list queries intentionally use lightweight ``frappe.get_all``
    projections. Document-scoped capability checks, however, must receive a
    real Door Cutting Order so the authorization gateway can enforce both the
    canonical capability matrix and Frappe's native document scope. Keep the
    resolved document request-local to avoid repeated loads without caching
    authorization-sensitive state across requests.
    """

    if getattr(order, "doctype", None) == _ORDER_DOCTYPE:
        return order

    name = _order_name(order)
    if not name:
        return None

    cache = getattr(frappe.local, _ORDER_DOCUMENT_CACHE_KEY, None)
    if cache is None:
        cache = {}
        setattr(frappe.local, _ORDER_DOCUMENT_CACHE_KEY, cache)

    document = cache.get(name)
    if document is None:
        document = frappe.get_doc(_ORDER_DOCTYPE, name)
        cache[name] = document
    return document


class FrappeShopFloorQueryRepository:
    """Frappe read adapter for shop-floor application queries."""

    def current_user(self) -> str:
        return frappe.session.user

    def session_identity(self) -> dict[str, Any]:
        user = self.current_user()
        full_name = frappe.get_cached_value("User", user, "full_name") or user
        roles = set(frappe.get_roles(user))
        departments: set[str] = set()
        for route in production_routing_repository.list_active_routes():
            departments.update(
                stage.department_label
                for stage in route.stages
                if stage.operational_role in roles or user == "Administrator"
            )
        return {
            "user": user,
            "full_name": full_name,
            "departments": sorted(departments),
        }

    def global_capabilities(self) -> frozenset[str]:
        return granted_capabilities(user=self.current_user())

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]:
        actor = str(user or self.current_user() or "").strip()
        if not actor:
            return ()
        return tuple(str(role) for role in frappe.get_roles(actor) if role)

    def is_admin(self) -> bool:
        return any(
            doctype_has_capability(capability)
            for capability in _SUPERVISOR_CAPABILITIES
        )

    def capabilities_for_order(self, order: Any) -> frozenset[str]:
        document = _order_document(order)
        if document is None:
            return frozenset()
        return frozenset(
            capability
            for capability in SHOP_FLOOR_DETAIL_CAPABILITIES
            if document_has_capability(document, capability)
        )

    def list_active_routes(self):
        return production_routing_repository.list_active_routes()

    def get_production_route(self, route_name: str):
        return production_routing_repository.get_route(route_name)

    def list_inbox_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        filters: dict[str, Any] = {
            "status": ["in", ["Pending", "In Progress", "Paused"]],
            "piece_label": ["is", "not set"],
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
                "department_label",
                "operational_role",
                "status",
                "assigned_to",
                "assignment_time",
                "sequence",
                "creation",
                "modified",
            ],
            order_by="assignment_time asc, creation asc",
        )

    def list_archive_stages(self, *, user: str, is_admin: bool) -> list[Any]:
        filters: dict[str, Any] = {
            "status": "Completed",
            "piece_label": ["is", "not set"],
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
                "department_label",
                "operational_role",
                "status",
                "assigned_to",
                "sequence",
                "finish_time",
                "modified",
            ],
            order_by="finish_time desc, modified desc",
            limit_page_length=100,
        )

    def personal_order_stage_timings(
        self,
        order_names: Sequence[str],
        *,
        user: str,
    ) -> dict[str, Any]:
        names = [str(name) for name in order_names if str(name or "").strip()]
        if not names:
            return {}
        placeholders = ", ".join(["%s"] * len(names))
        rows = frappe.db.sql(
            f"""
            select ps.door_cutting_order,
                   max(
                       case
                           when ps.name = dco.current_production_stage
                            and ps.status in ('Pending', 'In Progress', 'Paused')
                           then coalesce(ps.assignment_time, ps.creation)
                       end
                   ) as assignment_time,
                   max(
                       case
                           when ps.status = 'Completed'
                           then coalesce(ps.finish_time, ps.modified)
                       end
                   ) as completion_time
              from `tabProduction Stage` ps
              inner join `tabDoor Cutting Order` dco
                      on dco.name = ps.door_cutting_order
             where ps.assigned_to = %s
               and ifnull(ps.piece_label, '') = ''
               and ps.door_cutting_order in ({placeholders})
             group by ps.door_cutting_order
            """,
            [user, *names],
            as_dict=True,
        )
        return {str(row.door_cutting_order): row for row in rows}

    def current_stage_names(
        self,
        order_names: Sequence[str],
    ) -> dict[str, str | None]:
        if not order_names:
            return {}
        return {
            row.name: row.current_production_stage
            for row in frappe.get_all(
                _ORDER_DOCTYPE,
                filters={"name": ["in", list(order_names)]},
                fields=["name", "current_production_stage"],
            )
        }

    def order_summaries(self, order_names: Sequence[str]) -> dict[str, Any]:
        if not order_names:
            return {}
        rows = frappe.get_all(
            _ORDER_DOCTYPE,
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
                "drawing_dxf_status",
                "revision",
            ],
        )
        for row in rows:
            document = _order_document(row)
            facts = production_plan_facts(document) if document is not None else None
            # These three attributes preserve the application query shape while
            # deriving every operational value from canonical Cutting Plan state.
            # They are in-memory projections only; no DCO compatibility field is read.
            row.cutting_plan_json = (
                "canonical" if facts is not None and facts.has_cutting_plan else ""
            )
            row.plan_needs_recalculation = int(
                facts.plan_needs_recalculation if facts is not None else True
            )
            dxf_plan = latest_plan(str(row.name), source_type=UPLOADED_DXF)
            row.production_dxf = str(getattr(dxf_plan, "dxf_file", None) or "")
        return {row.name: row for row in rows}

    def get_order(self, order_name: str) -> Any:
        return frappe.get_doc(_ORDER_DOCTYPE, order_name)

    def can_view_order(self, order: Any) -> bool:
        if self.is_admin():
            return True
        user = self.current_user()
        if user == "Administrator":
            return True

        name = _order_name(order)
        if not name:
            return False
        if permissions._requires_assigned_scope(user):
            return permissions.worker_can_view_order(user, name)

        document = _order_document(order)
        return bool(
            document
            and frappe.has_permission(document, "read", user=user)
        )

    def list_order_stages(self, order_name: str) -> list[Any]:
        return frappe.get_all(
            "Production Stage",
            filters={
                "door_cutting_order": order_name,
            },
            fields=[
                "name",
                "stage_type",
                "department_label",
                "operational_role",
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
            [
                "name",
                "status",
                "stage_type",
                "department_label",
                "operational_role",
                "assigned_to",
            ],
            as_dict=True,
        )

    def load_plan_snapshot(
        self,
        order: Any,
        plan_source: str | None = None,
    ) -> dict[str, Any]:
        name = _order_name(order)
        if not name:
            return {}

        if plan_source == "System":
            plan = latest_plan(name, source_type=SYSTEM)
        elif plan_source == "Custom":
            plan = latest_plan(name, source_type=UPLOADED_DXF)
        else:
            plan = None
            approved_name = str(getattr(order, "approved_plan", None) or "").strip()
            if approved_name and frappe.db.exists("Cutting Plan", approved_name):
                candidate = frappe.get_doc("Cutting Plan", approved_name)
                if str(candidate.door_cutting_order or "") == name:
                    plan = candidate
            if plan is None:
                plan = current_working_plan(name)

        return self._parse_snapshot(getattr(plan, "snapshot_json", None) if plan else None)

    def user_can_view_dual_plans(self) -> bool:
        return any(
            doctype_has_capability(capability)
            for capability in (
                Capability.VIEW_SYSTEM_CUTTING_PLAN,
                Capability.VIEW_UPLOADED_CUTTING_PLAN,
                Capability.VIEW_APPROVED_CUTTING_PLAN,
                Capability.VIEW_CUTTING_PLAN,
            )
        )

    def get_order_status(self, order_name: str) -> str | None:
        return frappe.db.get_value(_ORDER_DOCTYPE, order_name, "status")

    def list_revert_stages(self, order_name: str) -> list[Any]:
        return frappe.get_all(
            "Production Stage",
            filters={
                "door_cutting_order": order_name,
                "status": ["in", ["Completed", "In Progress", "Paused", "Pending"]],
            },
            fields=[
                "name",
                "stage_type",
                "department_label",
                "operational_role",
                "status",
                "sequence",
                "assigned_to",
                "piece_label",
            ],
            order_by="sequence asc",
        )

    def get_users_for_role(self, role: str) -> list[dict[str, str]]:
        return shop_floor_authorization.get_users_for_role(role)

    def default_production_route(self) -> str | None:
        if not frappe.db.exists("DocType", "Almdina ERP Settings"):
            return None
        return frappe.db.get_single_value(
            "Almdina ERP Settings",
            "default_production_routing",
        ) or None

    @staticmethod
    def _parse_snapshot(raw: Any) -> dict[str, Any]:
        if not raw:
            return {}
        parsed = frappe.parse_json(raw) or {}
        return parsed if isinstance(parsed, dict) else {}
