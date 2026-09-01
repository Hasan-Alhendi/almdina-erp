from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe import (
    production_routing_repository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_query_repository import (
    FrappeShopFloorQueryRepository,
)


_ORDER_DOCTYPE = "Door Cutting Order"
_STAGE_DOCTYPE = "Production Stage"


class FrappeOrderListQueryRepository:
    """Focused bulk read adapter for the Door Cutting Order list endpoint.

    The detailed shop-floor repository still owns document/detail reads. This
    adapter composes it only for already-bulk helpers and adds the list-specific
    permission/stage projections required to keep query count bounded.
    """

    def __init__(self) -> None:
        self._shop_floor = FrappeShopFloorQueryRepository()

    def current_user(self) -> str:
        return self._shop_floor.current_user()

    def is_admin(self) -> bool:
        return self._shop_floor.is_admin()

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]:
        return self._shop_floor.actor_roles(user)

    def global_capabilities(self) -> frozenset[str]:
        return self._shop_floor.global_capabilities()

    def visible_order_names(self, order_names: Sequence[str]) -> frozenset[str]:
        names = [str(name).strip() for name in order_names if str(name or "").strip()]
        if not names:
            return frozenset()

        # frappe.get_list intentionally applies native DocType permissions,
        # user permissions and Almdina's permission_query_conditions. This one
        # query replaces per-row get_doc + has_permission checks without
        # broadening the user's document scope.
        rows = frappe.get_list(
            _ORDER_DOCTYPE,
            filters={"name": ["in", names]},
            fields=["name"],
            limit_page_length=max(len(names), 1),
        )
        return frozenset(str(row.name) for row in rows if row.name)

    def order_summaries(self, order_names: Sequence[str]) -> dict[str, Any]:
        return self._shop_floor.order_summaries(order_names)

    def stage_summaries(self, stage_names: Sequence[str]) -> dict[str, Any]:
        names = [str(name).strip() for name in stage_names if str(name or "").strip()]
        if not names:
            return {}
        rows = frappe.get_all(
            _STAGE_DOCTYPE,
            filters={"name": ["in", names]},
            fields=[
                "name",
                "status",
                "stage_type",
                "department_label",
                "operational_role",
                "assigned_to",
                "start_time",
            ],
            limit_page_length=max(len(names), 1),
        )
        return {str(row.name): row for row in rows if row.name}

    def personal_order_stage_timings(
        self,
        order_names: Sequence[str],
        *,
        user: str,
    ) -> dict[str, Any]:
        """Return personal timings plus the order-wide final completion in one query."""
        names = [str(name).strip() for name in order_names if str(name or "").strip()]
        if not names:
            return {}
        placeholders = ", ".join(["%s"] * len(names))
        rows = frappe.db.sql(
            f"""
            select ps.door_cutting_order,
                   max(
                       case
                           when ps.assigned_to = %s
                            and ps.name = dco.current_production_stage
                            and ps.status in ('Pending', 'In Progress', 'Paused')
                           then coalesce(ps.assignment_time, ps.creation)
                       end
                   ) as assignment_time,
                   max(
                       case
                           when ps.assigned_to = %s
                            and ps.status = 'Completed'
                           then coalesce(ps.finish_time, ps.modified)
                       end
                   ) as completion_time,
                   max(
                       case
                           when ps.status = 'Completed'
                           then coalesce(ps.finish_time, ps.modified)
                       end
                   ) as order_completion_time
              from `tabProduction Stage` ps
              inner join `tabDoor Cutting Order` dco
                      on dco.name = ps.door_cutting_order
             where ifnull(ps.piece_label, '') = ''
               and ps.door_cutting_order in ({placeholders})
             group by ps.door_cutting_order
            """,
            [user, user, *names],
            as_dict=True,
        )
        return {str(row.door_cutting_order): row for row in rows}

    def production_routes(self, route_names: Sequence[str]) -> dict[str, Any]:
        routes: dict[str, Any] = {}
        for route_name in dict.fromkeys(
            str(value).strip() for value in route_names if str(value or "").strip()
        ):
            try:
                routes[route_name] = production_routing_repository.get_route(route_name)
            except (ValueError, AttributeError):
                continue
        return routes

    def department_filter_options(self) -> list[dict[str, str]]:
        """Unique required stages from enabled routes: stage_type + visible label."""

        route_names = frappe.get_all(
            "Production Routing",
            filters={"disabled": 0},
            pluck="name",
            limit_page_length=200,
        )
        names = [str(name).strip() for name in route_names if str(name or "").strip()]
        if not names:
            return []
        rows = frappe.get_all(
            "Production Routing Stage",
            filters={
                "parent": ["in", names],
                "parenttype": "Production Routing",
                "required": 1,
            },
            fields=["stage_type", "department_label"],
            order_by="parent asc, sequence asc, idx asc",
            limit_page_length=500,
        )
        return [
            {
                "stage_type": str(row.stage_type or "").strip(),
                "department_label": str(row.department_label or "").strip(),
            }
            for row in rows
        ]


__all__ = ["FrappeOrderListQueryRepository"]
