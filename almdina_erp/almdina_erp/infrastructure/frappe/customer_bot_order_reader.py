"""Customer-scoped Door Cutting Order reads for the customer bot.

Queries constrain by customer or exact document name. Stage and route rows
are loaded in batches. This module does not save, recalculate, or send.
"""

from __future__ import annotations

from collections.abc import Mapping

import frappe

from almdina_erp.almdina_erp.application.customer_bot.order_followup_ports import (
    CustomerOrderHeader,
    ProductionStageFacts,
)
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    non_current_revision_states,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)

CUSTOMER_ORDER_PAGE_SIZE = 200
_MAX_OFFSET = 100_000
_ORDER_TABLE = "tabDoor Cutting Order"
_STAGE_TABLE = "tabProduction Stage"
_ROUTING_TABLE = "tabProduction Routing"
_ROUTING_STAGE_TABLE = "tabProduction Routing Stage"
_DEFINITION_TABLE = "tabProduction Stage Definition"
_EXCLUDED_STATUSES = ("Delivered", "Cancelled")


class CustomerOrderReadError(RuntimeError):
    """Raised when a paged read would otherwise stop before the last row."""


class FrappeCustomerOrderReader:
    """Header, stage, and route-terminal ports backed by one batched read."""

    def __init__(self, page_size: int = CUSTOMER_ORDER_PAGE_SIZE) -> None:
        if page_size < 1 or page_size > CUSTOMER_ORDER_PAGE_SIZE:
            raise ValueError("customer order page size is outside the supported range")
        self.page_size = page_size

    def list_current_headers(self, customer_id: str) -> tuple[CustomerOrderHeader, ...]:
        customer = str(customer_id or "").strip()
        if not customer:
            return ()
        excluded_status = ", ".join(["%s"] * len(_EXCLUDED_STATUSES))
        excluded_revision = ", ".join(["%s"] * len(non_current_revision_states()))
        headers: list[CustomerOrderHeader] = []
        offset = 0
        while offset <= _MAX_OFFSET:
            rows = frappe.db.sql(
                f"""
                SELECT name, customer, order_date, status, production_path,
                       current_production_stage, revision_state
                FROM `{_ORDER_TABLE}`
                WHERE customer = %s
                  AND IFNULL(status, 'Draft') NOT IN ({excluded_status})
                  AND IFNULL(revision_state, '') NOT IN ({excluded_revision})
                ORDER BY order_date DESC, name DESC
                LIMIT %s OFFSET %s
                """,
                (
                    customer,
                    *_EXCLUDED_STATUSES,
                    *tuple(sorted(non_current_revision_states())),
                    self.page_size,
                    offset,
                ),
                as_dict=True,
            )
            batch = tuple(rows or ())
            headers.extend(
                header
                for header in (_header(row) for row in batch)
                if header.customer_id == customer
            )
            if len(batch) < self.page_size:
                return tuple(headers)
            offset += self.page_size
        raise CustomerOrderReadError("customer order read exceeded its page bound")

    def get_header_by_exact_name(self, order_name: str) -> CustomerOrderHeader | None:
        token = str(order_name or "")
        if not token:
            return None
        rows = frappe.db.sql(
            f"""
            SELECT name, customer, order_date, status, production_path,
                   current_production_stage, revision_state
            FROM `{_ORDER_TABLE}`
            WHERE name = %s
            LIMIT 2
            """,
            (token,),
            as_dict=True,
        )
        matches = tuple(rows or ())
        if len(matches) != 1:
            return None
        header = _header(matches[0])
        if header.name != token:
            return None
        return header

    def stages_for_orders(
        self, pointers: tuple[tuple[str, str], ...]
    ) -> Mapping[str, ProductionStageFacts]:
        expected = {
            stage_name: order_name
            for order_name, stage_name in pointers
            if order_name and stage_name
        }
        if not expected:
            return {}
        placeholders = ", ".join(["%s"] * len(expected))
        rows = frappe.db.sql(
            f"""
            SELECT name, status, stage_type, door_cutting_order
            FROM `{_STAGE_TABLE}`
            WHERE name IN ({placeholders})
            """,
            tuple(expected),
            as_dict=True,
        )
        facts: dict[str, ProductionStageFacts] = {}
        for row in rows or ():
            stage_name = str(row.get("name") or "")
            if expected.get(stage_name) != str(row.get("door_cutting_order") or ""):
                continue
            facts[stage_name] = ProductionStageFacts(
                name=stage_name,
                status=str(row.get("status") or ""),
                stage_type=str(row.get("stage_type") or ""),
            )
        return facts

    def terminal_by_path_and_stage(
        self, keys: tuple[tuple[str, str], ...]
    ) -> Mapping[tuple[str, str], bool | None]:
        unique_keys = tuple(dict.fromkeys(key for key in keys if key[0] and key[1]))
        routes = _routes_for(tuple(dict.fromkeys(path for path, _stage in unique_keys)))
        flags: dict[tuple[str, str], bool | None] = {}
        for path, stage_type in unique_keys:
            route = routes.get(path)
            if route is None or not route.contains(stage_type):
                flags[(path, stage_type)] = None
                continue
            flags[(path, stage_type)] = route.next_stage(stage_type) is None
        return flags


def _routes_for(paths: tuple[str, ...]) -> dict[str, ProductionRoute]:
    if not paths:
        return {}
    path_placeholders = ", ".join(["%s"] * len(paths))
    routing_rows = frappe.db.sql(
        f"""
        SELECT name, disabled
        FROM `{_ROUTING_TABLE}`
        WHERE name IN ({path_placeholders})
        """,
        paths,
        as_dict=True,
    )
    enabled = {
        str(row.get("name") or "")
        for row in routing_rows or ()
        if not int(row.get("disabled") or 0)
    }
    if not enabled:
        return {}
    enabled_names = tuple(sorted(enabled))
    enabled_placeholders = ", ".join(["%s"] * len(enabled_names))
    stage_rows = frappe.db.sql(
        f"""
        SELECT parent, sequence, stage_definition, operational_role, is_planning_stage
        FROM `{_ROUTING_STAGE_TABLE}`
        WHERE parenttype = 'Production Routing'
          AND required = 1
          AND parent IN ({enabled_placeholders})
        ORDER BY parent ASC, sequence ASC
        """,
        enabled_names,
        as_dict=True,
    )
    definition_names = tuple(
        dict.fromkeys(
            str(row.get("stage_definition") or "")
            for row in stage_rows or ()
            if row.get("stage_definition")
        )
    )
    labels = _definition_labels(definition_names)
    grouped: dict[str, list[RoutingStage]] = {}
    for row in stage_rows or ():
        parent = str(row.get("parent") or "")
        definition = str(row.get("stage_definition") or "")
        label = labels.get(definition) or definition
        role = str(row.get("operational_role") or "").strip()
        sequence = int(row.get("sequence") or 0)
        if not parent or not definition or not label or not role or sequence <= 0:
            continue
        grouped.setdefault(parent, []).append(
            RoutingStage(
                sequence=sequence,
                stage_type=definition,
                department_label=label,
                operational_role=role,
                is_planning_stage=bool(int(row.get("is_planning_stage") or 0)),
            )
        )
    routes: dict[str, ProductionRoute] = {}
    for name, stages in grouped.items():
        try:
            routes[name] = ProductionRoute(name=name, label=name, stages=tuple(stages))
        except ValueError:
            continue
    return routes


def _definition_labels(names: tuple[str, ...]) -> dict[str, str]:
    if not names:
        return {}
    placeholders = ", ".join(["%s"] * len(names))
    rows = frappe.db.sql(
        f"""
        SELECT name, stage_label
        FROM `{_DEFINITION_TABLE}`
        WHERE name IN ({placeholders})
        """,
        names,
        as_dict=True,
    )
    return {
        str(row.get("name") or ""): str(row.get("stage_label") or "").strip()
        for row in rows or ()
        if row.get("name")
    }


def _header(row: Mapping[str, object]) -> CustomerOrderHeader:
    return CustomerOrderHeader(
        name=str(row.get("name") or ""),
        customer_id=str(row.get("customer") or ""),
        order_date=_iso_date(row.get("order_date")),
        stored_status=str(row.get("status") or "") or "Draft",
        revision_state=str(row.get("revision_state") or ""),
        production_path=str(row.get("production_path") or ""),
        current_stage_name=str(row.get("current_production_stage") or ""),
    )


def _iso_date(value: object) -> str | None:
    if value is None:
        return None
    text = value.isoformat() if hasattr(value, "isoformat") else str(value).strip()
    text = str(text or "").strip()
    return text[:10] if text else None


__all__ = [
    "CUSTOMER_ORDER_PAGE_SIZE",
    "CustomerOrderReadError",
    "FrappeCustomerOrderReader",
]
