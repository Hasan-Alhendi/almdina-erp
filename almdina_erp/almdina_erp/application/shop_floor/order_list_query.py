from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from almdina_erp.almdina_erp.domain.orders.lifecycle import normalize_order_status
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    build_production_action_context,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import ProductionRoute
from almdina_erp.almdina_erp.domain.orders.stage_operational_access import (
    actor_holds_operational_role,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


_LIST_ACTION_CAPABILITIES = frozenset(
    {
        Capability.START_ASSIGNED_STAGE,
        Capability.HANDOFF_ASSIGNED_STAGE,
        Capability.MARK_DELIVERED,
    }
)


class OrderListQueryPort(Protocol):
    """Read-only port for the Door Cutting Order list projection.

    The list endpoint deliberately owns a bulk projection instead of reusing the
    detail-query repository one document at a time. Visibility is resolved in a
    single native Frappe list query by the infrastructure adapter; the application
    layer then evaluates the same production domain policy over already-visible
    orders.
    """

    def current_user(self) -> str: ...

    def is_admin(self) -> bool: ...

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]: ...

    def global_capabilities(self) -> frozenset[str]: ...

    def visible_order_names(self, order_names: Sequence[str]) -> frozenset[str]: ...

    def order_summaries(self, order_names: Sequence[str]) -> Mapping[str, Any]: ...

    def stage_summaries(self, stage_names: Sequence[str]) -> Mapping[str, Any]: ...

    def personal_order_stage_timings(
        self,
        order_names: Sequence[str],
        *,
        user: str,
    ) -> Mapping[str, Any]: ...

    def production_routes(
        self,
        route_names: Sequence[str],
    ) -> Mapping[str, ProductionRoute]: ...

    def department_filter_options(self) -> Sequence[Mapping[str, str]]: ...


def _value(row: Any, fieldname: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(fieldname, default)
    return getattr(row, fieldname, default)


def _as_bool(value: Any) -> bool:
    try:
        return bool(int(value or 0))
    except (TypeError, ValueError):
        return bool(value)


def overview_order_list_delivered_rank(status: str | None) -> int:
    """Return 1 for delivered orders so they sort after every other status."""

    return 1 if normalize_order_status(status) == "Delivered" else 0


def sort_overview_order_list(rows: Sequence[Any]) -> list[Any]:
    """Sort all-orders rows: non-delivered first, then modified newest-first.

    Delivered rows stay last. Within each group, missing ``modified`` sorts last
    and equal timestamps break ties by document name.
    """

    named = sorted(rows, key=lambda row: str(_value(row, "name") or ""))
    by_modified = sorted(
        named,
        key=lambda row: str(_value(row, "modified") or ""),
        reverse=True,
    )
    return sorted(
        by_modified,
        key=lambda row: overview_order_list_delivered_rank(_value(row, "status")),
    )


def _normalize_order_names(order_names: Any) -> list[str]:
    if isinstance(order_names, str):
        raw = order_names.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                order_names = json.loads(raw)
            except ValueError:
                order_names = [raw]
        else:
            order_names = [part.strip() for part in raw.split(",")]
    if not isinstance(order_names, (list, tuple, set)):
        return []

    seen: set[str] = set()
    normalized: list[str] = []
    for value in order_names:
        name = str(value or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def _resolve_operational_role(
    order: Any,
    stage: Any | None,
    routes: Mapping[str, ProductionRoute],
) -> str | None:
    if not stage:
        return None

    stored_role = str(_value(stage, "operational_role") or "").strip()
    if stored_role:
        return stored_role

    route_name = str(_value(order, "production_path") or "").strip()
    stage_type = str(_value(stage, "stage_type") or "").strip()
    route = routes.get(route_name)
    if not route or not stage_type:
        return None
    try:
        return str(route.stage(stage_type).operational_role or "").strip() or None
    except ValueError:
        return None


def _production_facts(
    *,
    actor: str,
    actor_roles: tuple[str, ...],
    order: Any,
    stage: Any | None,
    operational_role: str | None,
) -> ProductionActionFacts:
    return ProductionActionFacts(
        order_status=_value(order, "status"),
        production_path=_value(order, "production_path"),
        current_stage_name=_value(order, "current_production_stage"),
        has_cutting_plan=bool(_value(order, "cutting_plan_json")),
        plan_needs_recalculation=_as_bool(_value(order, "plan_needs_recalculation")),
        stage_name=_value(stage, "name") if stage else None,
        stage_type=_value(stage, "stage_type") if stage else None,
        stage_status=_value(stage, "status") if stage else None,
        assigned_to=_value(stage, "assigned_to") if stage else None,
        actor=actor,
        drawing_dxf_status=_value(order, "drawing_dxf_status"),
        operational_role=operational_role,
        actor_roles=actor_roles,
        # Preserve the existing command/query contract: only the built-in
        # Administrator bypasses the operational-role requirement. Supervisors
        # remain capability-driven and do not impersonate a worker role.
        is_admin=actor == "Administrator",
    )


def _handoff_visible(
    *,
    authorized: bool,
    order: Any,
    stage: Any | None,
    routes: Mapping[str, ProductionRoute],
) -> bool:
    if not authorized or not stage:
        return False

    route_name = str(_value(order, "production_path") or "").strip()
    stage_type = str(_value(stage, "stage_type") or "").strip()
    route = routes.get(route_name)
    if not route:
        # Matches the legacy list projection: absence of route metadata does not
        # invent a new authorization denial. The command endpoint still validates
        # the workflow before mutation.
        return True
    try:
        route.stage(stage_type)
    except ValueError:
        # Structural route corruption is the one readiness condition that hides
        # handoff. Plan approval/recalculation remains visible so the worker can
        # receive the established Arabic readiness message on action.
        return False
    return True


def get_order_operational_role_flags(
    repository: OrderListQueryPort,
    order_names: Any = None,
) -> dict[str, Any]:
    """Build the worker/list presentation projection with bounded bulk reads.

    Query growth is based on unique data sets (visible orders, active stages and
    production routes), never one document load or one permission check per row.
    Server command endpoints remain the final mutation authority.
    """

    actor = str(repository.current_user() or "").strip()
    if not actor or actor == "Guest":
        return {"personal_view": False, "orders": {}}

    names = _normalize_order_names(order_names)
    personal_view = actor != "Administrator" and not repository.is_admin()
    if not names:
        return {"personal_view": personal_view, "orders": {}}

    visible = repository.visible_order_names(names)
    visible_names = [name for name in names if name in visible]
    if not visible_names:
        return {"personal_view": personal_view, "orders": {}}

    orders = repository.order_summaries(visible_names)
    stage_names = sorted(
        {
            str(_value(order, "current_production_stage") or "").strip()
            for order in orders.values()
            if str(_value(order, "current_production_stage") or "").strip()
        }
    )
    stages = repository.stage_summaries(stage_names)
    route_names = sorted(
        {
            str(_value(order, "production_path") or "").strip()
            for order in orders.values()
            if str(_value(order, "production_path") or "").strip()
        }
    )
    routes = repository.production_routes(route_names)
    personal_timings = (
        repository.personal_order_stage_timings(visible_names, user=actor)
        if personal_view
        else {}
    )

    actor_roles = repository.actor_roles(actor)
    # List actions are custom order capabilities. The adapter's one bulk
    # visible_order_names() query is the native read narrowing that
    # document_has_capability previously repeated for every capability and row.
    action_capabilities = frozenset(
        capability
        for capability in repository.global_capabilities()
        if capability in _LIST_ACTION_CAPABILITIES
    )

    flags: dict[str, dict[str, Any]] = {}
    for name in visible_names:
        order = orders.get(name)
        if not order:
            continue

        stage_name = str(_value(order, "current_production_stage") or "").strip()
        stage = stages.get(stage_name) if stage_name else None
        operational_role = _resolve_operational_role(order, stage, routes)
        actions = build_production_action_context(
            capabilities=action_capabilities,
            facts=_production_facts(
                actor=actor,
                actor_roles=actor_roles,
                order=order,
                stage=stage,
                operational_role=operational_role,
            ),
        )
        actor_holds_current_role = actor_holds_operational_role(
            actor_roles,
            operational_role,
            is_admin=False,
        )
        is_current_assignee = bool(
            actor_holds_current_role
            and stage
            and str(_value(stage, "assigned_to") or "").strip() == actor
        )
        timing = personal_timings.get(name) or {}
        flags[name] = {
            "actor_holds_current_stage_role": actor_holds_current_role,
            "is_current_assignee": is_current_assignee,
            "assignment_state": "assigned" if is_current_assignee else "completed",
            "assignment_time": _value(timing, "assignment_time"),
            "start_time": _value(stage, "start_time") if stage else None,
            "completion_time": _value(timing, "completion_time"),
            "ready_for_delivery_time": _value(timing, "order_completion_time"),
            "current_stage_operational_role": operational_role,
            "active_stage_name": _value(stage, "name") if stage else stage_name or None,
            "can_start_stage": bool(
                actions[Capability.START_ASSIGNED_STAGE]["allowed"]
            ),
            "can_handoff_stage": _handoff_visible(
                authorized=bool(
                    actions[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"]
                ),
                order=order,
                stage=stage,
                routes=routes,
            ),
            "can_mark_delivered": bool(
                actions[Capability.MARK_DELIVERED]["allowed"]
            ),
        }

    return {"personal_view": personal_view, "orders": flags}


def get_department_filter_options(
    repository: OrderListQueryPort,
) -> list[dict[str, str]]:
    """Return unique operational stage identities for the DCO list shortcut.

    Display stays on the Arabic department label. Query identity is ``stage_type``.
    The payload is operational only: no role names, costs, or routing internals.
    """

    actor = str(repository.current_user() or "").strip()
    if not actor or actor == "Guest":
        return []
    if actor != "Administrator" and not repository.is_admin():
        if Capability.VIEW_ORDERS not in repository.global_capabilities():
            return []

    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in repository.department_filter_options():
        stage_type = str(_value(row, "stage_type") or "").strip()
        label = str(_value(row, "department_label") or stage_type).strip()
        if not stage_type or stage_type in seen:
            continue
        seen.add(stage_type)
        options.append({
            "stage_type": stage_type,
            "department_label": label or stage_type,
        })
    return options


__all__ = [
    "OrderListQueryPort",
    "get_department_filter_options",
    "get_order_operational_role_flags",
    "overview_order_list_delivered_rank",
    "sort_overview_order_list",
]
