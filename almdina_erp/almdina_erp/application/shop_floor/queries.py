from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    department_for_stage_type,
    department_status_for_stage_status,
    normalize_order_status,
    PRE_PRODUCTION_ORDER_STATUSES,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    build_production_action_context,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import ProductionRoute
from almdina_erp.almdina_erp.domain.orders.stage_operational_access import (
    actor_holds_operational_role,
    decide_stage_scoped_mutation,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    DRAWING_CAPABILITIES,
    PLANNING_CAPABILITIES,
    PRODUCTION_CAPABILITIES,
    SHOP_FLOOR_ACCESS_CAPABILITIES,
    Capability,
)


SHOP_FLOOR_DETAIL_CAPABILITIES = frozenset(
    PLANNING_CAPABILITIES | DRAWING_CAPABILITIES | PRODUCTION_CAPABILITIES
)
_HANDOFF_READINESS_BLOCK_CODES = frozenset(
    {"plan_not_approved", "approved_plan_stale"}
)


class ShopFloorQueryError(ValueError):
    """Raised when a shop-floor read use case cannot be completed."""


class ShopFloorPermissionDenied(PermissionError):
    """Raised when the current user cannot view shop-floor data."""


class ShopFloorQueryPort(Protocol):
    def current_user(self) -> str: ...

    def session_identity(self) -> dict[str, Any]: ...

    def global_capabilities(self) -> frozenset[str]: ...

    def is_admin(self) -> bool: ...

    def actor_roles(self, user: str | None = None) -> tuple[str, ...]: ...

    def capabilities_for_order(self, order: Any) -> frozenset[str]: ...

    def list_active_routes(self) -> list[ProductionRoute]: ...

    def get_production_route(self, route_name: str) -> ProductionRoute: ...

    def list_inbox_stages(self, *, user: str, is_admin: bool) -> list[Any]: ...

    def list_archive_stages(self, *, user: str, is_admin: bool) -> list[Any]: ...

    def current_stage_names(
        self,
        order_names: Sequence[str],
    ) -> Mapping[str, str | None]: ...

    def order_summaries(self, order_names: Sequence[str]) -> Mapping[str, Any]: ...

    def personal_order_stage_timings(
        self,
        order_names: Sequence[str],
        *,
        user: str,
    ) -> Mapping[str, Any]: ...

    def get_order(self, order_name: str) -> Any: ...

    def can_view_order(self, order: Any) -> bool: ...

    def list_order_stages(self, order_name: str) -> list[Any]: ...

    def get_stage_summary(self, stage_name: str) -> Any | None: ...

    def load_plan_snapshot(
        self,
        order: Any,
        plan_source: str | None = None,
    ) -> dict[str, Any]: ...

    def user_can_view_dual_plans(self) -> bool: ...

    def get_order_status(self, order_name: str) -> str | None: ...

    def list_revert_stages(self, order_name: str) -> list[Any]: ...

    def get_users_for_role(self, role: str) -> list[dict[str, str]]: ...

    def default_production_route(self) -> str | None: ...


def _production_route(
    repository: ShopFloorQueryPort,
    route_name: str,
) -> ProductionRoute | None:
    try:
        return repository.get_production_route(route_name)
    except (ValueError, AttributeError):
        return None


def _value(row: Any, fieldname: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(fieldname, default)
    return getattr(row, fieldname, default)


def _as_bool(value: Any) -> bool:
    try:
        return bool(int(value or 0))
    except (TypeError, ValueError):
        return bool(value)


def _assert_shop_floor_access(repository: ShopFloorQueryPort) -> frozenset[str]:
    user = repository.current_user()
    capabilities = repository.global_capabilities()
    if user == "Guest" or not capabilities.intersection(
        SHOP_FLOOR_ACCESS_CAPABILITIES
    ):
        raise ShopFloorPermissionDenied("لا تملك صلاحية الدخول إلى صالة الإنتاج.")
    return capabilities


def get_shop_floor_context(repository: ShopFloorQueryPort) -> dict[str, Any]:
    capabilities = _assert_shop_floor_access(repository)
    identity = dict(repository.session_identity())
    identity.pop("roles", None)
    routes = [
        {
            "name": route.name,
            "label": route.label,
            "stages": [
                {
                    "sequence": stage.sequence,
                    "stage_type": stage.stage_type,
                    "department": stage.department_label,
                    "is_planning_stage": stage.is_planning_stage,
                }
                for stage in route.stages
            ],
        }
        for route in repository.list_active_routes()
    ]
    return {
        "identity": identity,
        "navigation": build_navigation_context(capabilities),
        # The board needs the configured workflow order, but never needs role
        # names. Command authorization and worker selection remain server-side.
        "production_routes": routes,
        # Workers only ever see their own stages, so their list can safely append
        # what they already finished. A supervisor's inbox spans the whole floor
        # and stays limited to the active work.
        "personal_inbox": not repository.is_admin(),
        "capabilities": {
            capability: capability in capabilities
            for capability in sorted(SHOP_FLOOR_ACCESS_CAPABILITIES)
        },
    }


def _filter_active_stages(
    repository: ShopFloorQueryPort,
    stages: list[Any],
) -> list[Any]:
    if not stages:
        return []
    order_names = sorted(
        {
            str(_value(row, "door_cutting_order") or "")
            for row in stages
            if _value(row, "door_cutting_order")
        }
    )
    if not order_names:
        return stages
    current_by_order = repository.current_stage_names(order_names)
    return [
        row
        for row in stages
        if not current_by_order.get(str(_value(row, "door_cutting_order") or ""))
        or _value(row, "name")
        == current_by_order.get(str(_value(row, "door_cutting_order") or ""))
    ]


def _planning_handoff_block(
    route: ProductionRoute | None,
    order: Any,
    stage_type: str,
) -> tuple[str | None, str]:
    if not route:
        return None, ""
    try:
        route_stage = route.stage(stage_type)
    except ValueError:
        return "invalid_route_stage", "المرحلة الحالية ليست ضمن مسار الإنتاج المحدد."
    if not route_stage.is_planning_stage:
        return None, ""
    if not _value(order, "approved_plan"):
        return (
            "plan_not_approved",
            "اعتمد خطة القص بعد مراجعتها قبل تسليم مرحلة التخطيط إلى القسم التالي.",
        )
    if _as_bool(_value(order, "plan_needs_recalculation")):
        return (
            "approved_plan_stale",
            "خطة القص تغيّرت وتحتاج إلى إعادة حساب واعتماد جديد قبل مغادرة مرحلة التخطيط.",
        )
    return None, ""


def _handoff_visibility(
    actions: Mapping[str, Mapping[str, Any]],
    handoff_code: str | None,
) -> bool:
    """Return whether the authorized worker should see the handoff action.

    Planning readiness is intentionally separate from authorization: an assigned
    worker who owns the handoff capability must still see «إنهاء العمل» while
    the plan needs approval/recalculation. The command layer remains the final
    gate and reports that readiness reason when the worker tries to finish.
    Structural route corruption still hides the action because it cannot be
    completed until the route itself is repaired.
    """

    authorized = bool(actions[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"])
    return bool(
        authorized
        and (
            not handoff_code
            or handoff_code in _HANDOFF_READINESS_BLOCK_CODES
        )
    )


def _enrich_stage_rows(
    repository: ShopFloorQueryPort,
    stages: list[Any],
) -> list[dict[str, Any]]:
    if not stages:
        return []
    order_names = sorted(
        {
            str(_value(row, "door_cutting_order") or "")
            for row in stages
            if _value(row, "door_cutting_order")
        }
    )
    orders = repository.order_summaries(order_names)
    actor = repository.current_user()
    actor_roles = repository.actor_roles(actor)
    is_admin = bool(repository.is_admin() or actor == "Administrator")
    current_stages: dict[str, Any] = {}
    for order in orders.values():
        stage_name = str(_value(order, "current_production_stage") or "").strip()
        if stage_name and stage_name not in current_stages:
            current_stages[stage_name] = repository.get_stage_summary(stage_name)

    enriched: list[dict[str, Any]] = []
    for stage in stages:
        order_name = str(_value(stage, "door_cutting_order") or "")
        order = orders.get(order_name) or {}
        production_path = _value(order, "production_path")
        stage_type = str(_value(stage, "stage_type") or "")
        can_handoff_to = None
        route = _production_route(repository, str(production_path or ""))
        if route:
            try:
                next_stage = route.next_stage(stage_type)
                can_handoff_to = next_stage.stage_type if next_stage else None
            except ValueError:
                can_handoff_to = None
        actions = build_production_action_context(
            capabilities=repository.capabilities_for_order(order),
            facts=_production_facts(repository, order, stage),
        )
        handoff_code, handoff_reason = _planning_handoff_block(
            route,
            order,
            stage_type,
        )
        can_handoff = _handoff_visibility(actions, handoff_code)
        current_stage_name = str(_value(order, "current_production_stage") or "").strip()
        current_stage = current_stages.get(current_stage_name)
        current_role = (
            _resolve_operational_role(repository, order, current_stage)
            if current_stage
            else None
        )
        enriched.append(
            {
                **dict(stage),
                "customer": _value(order, "customer"),
                "order_date": _value(order, "order_date"),
                "board_description": _value(order, "board_description"),
                "edge_color": _value(order, "edge_color"),
                "order_status": _value(order, "status"),
                "production_path": production_path,
                "current_department": _value(order, "current_department"),
                "department_status": _value(order, "department_status")
                or department_status_for_stage_status(str(_value(stage, "status") or "")),
                "approved_plan": _value(order, "approved_plan"),
                "production_dxf": _value(order, "production_dxf"),
                "drawing_dxf_status": _value(order, "drawing_dxf_status"),
                "revision": _value(order, "revision"),
                "department_label": _value(stage, "department_label")
                or department_for_stage_type(stage_type)
                or stage_type,
                "operational_role": _resolve_operational_role(repository, order, stage),
                "current_production_stage": current_stage_name or None,
                "current_stage_type": (
                    str(_value(current_stage, "stage_type") or "") or None
                    if current_stage
                    else None
                ),
                "current_stage_operational_role": current_role,
                # True only while the order sits on a stage whose operational role
                # the actor holds — that is the work they can still act on.
                "actor_holds_current_stage_role": actor_holds_operational_role(
                    actor_roles,
                    current_role,
                    is_admin=is_admin,
                ),
                "can_handoff_to": can_handoff_to,
                "can_start_stage": bool(actions[Capability.START_ASSIGNED_STAGE]["allowed"]),
                "can_handoff_stage": can_handoff,
                "handoff_block_code": handoff_code or "",
                "handoff_block_reason": handoff_reason,
            }
        )
    return enriched


def get_my_inbox(repository: ShopFloorQueryPort) -> list[dict[str, Any]]:
    _assert_shop_floor_access(repository)
    user = repository.current_user()
    is_admin = repository.is_admin()
    stages = repository.list_inbox_stages(user=user, is_admin=is_admin)
    rows = _enrich_stage_rows(repository, _filter_active_stages(repository, stages))
    # Workers only see orders whose current stage matches their operational
    # role. Completed work they touched stays in get_my_archive().
    if not is_admin and user != "Administrator":
        rows = [
            row
            for row in rows
            if row.get("actor_holds_current_stage_role")
        ]
    return rows


def get_my_archive(repository: ShopFloorQueryPort) -> list[dict[str, Any]]:
    _assert_shop_floor_access(repository)
    user = repository.current_user()
    is_admin = repository.is_admin()
    stages = repository.list_archive_stages(user=user, is_admin=is_admin)
    rows = _enrich_stage_rows(repository, stages)
    if not is_admin and user != "Administrator":
        rows = [
            row
            for row in rows
            if normalize_order_status(row.get("order_status"))
            not in PRE_PRODUCTION_ORDER_STATUSES
        ]
    return rows


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
    names: list[str] = []
    for value in order_names:
        name = str(value or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def get_order_operational_role_flags(
    repository: ShopFloorQueryPort,
    order_names: Any = None,
) -> dict[str, Any]:
    """Return role classification and server-authorized quick actions per order.

    Used by the shared Door Cutting Order list to put a worker's current
    assignments first, then their completed work in a green trailer section,
    while rendering only actions currently allowed by the domain policy.
    Supervisors keep an unmarked list.
    """

    actor = str(repository.current_user() or "").strip()
    if not actor or actor == "Guest":
        return {"personal_view": False, "orders": {}}

    names = _normalize_order_names(order_names)
    personal_view = actor != "Administrator" and not repository.is_admin()
    if not names:
        return {"personal_view": personal_view, "orders": {}}

    orders = repository.order_summaries(names)
    timing_loader = getattr(repository, "personal_order_stage_timings", None)
    personal_timings = (
        timing_loader(names, user=actor)
        if personal_view and callable(timing_loader)
        else {}
    )
    actor_roles = repository.actor_roles(actor)
    flags: dict[str, dict[str, Any]] = {}
    current_stages: dict[str, Any] = {}
    for name in names:
        order = orders.get(name)
        if not order:
            continue
        if not repository.can_view_order(order):
            continue
        stage_name = str(_value(order, "current_production_stage") or "").strip()
        current_stage = None
        if stage_name:
            if stage_name not in current_stages:
                current_stages[stage_name] = repository.get_stage_summary(stage_name)
            current_stage = current_stages.get(stage_name)
        role = (
            _resolve_operational_role(repository, order, current_stage)
            if current_stage
            else None
        )
        stage_snapshot = _active_stage_snapshot(
            repository,
            order,
            repository.capabilities_for_order(order),
        )
        actor_holds_current_role = actor_holds_operational_role(
            actor_roles,
            role,
            is_admin=False,
        )
        is_current_assignee = bool(
            actor_holds_current_role
            and stage_snapshot.get("active_stage_assigned_to") == actor
        )
        timing = personal_timings.get(name) or {}
        flags[name] = {
            "actor_holds_current_stage_role": actor_holds_current_role,
            "is_current_assignee": is_current_assignee,
            "assignment_state": "assigned" if is_current_assignee else "completed",
            "assignment_time": _value(timing, "assignment_time"),
            "completion_time": _value(timing, "completion_time"),
            "current_stage_operational_role": role,
            # List actions are presentation hints from the same server policy
            # used by the command endpoints. The commands still authorize again.
            "active_stage_name": stage_snapshot.get("active_stage_name"),
            "can_start_stage": stage_snapshot.get("can_start_stage") is True,
            "can_handoff_stage": stage_snapshot.get("can_handoff_stage") is True,
        }
    return {"personal_view": personal_view, "orders": flags}


def _resolve_operational_role(
    repository: ShopFloorQueryPort,
    order: Any,
    stage: Any | None,
) -> str | None:
    if not stage:
        return None
    role = str(_value(stage, "operational_role") or "").strip()
    if role:
        return role
    route = _production_route(repository, str(_value(order, "production_path") or ""))
    stage_type = str(_value(stage, "stage_type") or "").strip()
    if not route or not stage_type:
        return None
    try:
        return str(route.stage(stage_type).operational_role or "").strip() or None
    except ValueError:
        return None


def _production_facts(
    repository: ShopFloorQueryPort,
    order: Any,
    stage: Any | None = None,
) -> ProductionActionFacts:
    actor = repository.current_user()
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
        operational_role=_resolve_operational_role(repository, order, stage),
        actor_roles=repository.actor_roles(actor),
        is_admin=actor == "Administrator",
    )


def _assert_query_action(
    repository: ShopFloorQueryPort,
    order: Any,
    action: str,
    *,
    stage: Any | None = None,
) -> None:
    decision = decide_production_action(
        action,
        capabilities=repository.capabilities_for_order(order),
        facts=_production_facts(repository, order, stage),
    )
    if decision.allowed:
        return
    if decision.code == "missing_capability":
        raise ShopFloorPermissionDenied(decision.reason)
    raise ShopFloorQueryError(decision.reason)


def get_dispatch_options(
    repository: ShopFloorQueryPort,
    order_name: str,
) -> dict[str, Any]:
    order = repository.get_order(order_name)
    _assert_query_action(repository, order, Capability.DISPATCH_ORDER)
    routes = repository.list_active_routes()
    if not routes:
        raise ShopFloorQueryError(
            "أنشئ مسار إنتاج وفعّله قبل إرسال الطلبات إلى الإنتاج."
        )
    available_names = {route.name for route in routes}
    configured_default = repository.default_production_route()
    path_rows = []
    for route in routes:
        path_rows.append(
            {
                "value": route.name,
                "label": route.label,
                "first_stage_type": route.first_stage.stage_type,
                "department": route.first_stage.department_label,
                "operational_role": route.first_stage.operational_role,
                "stage_count": len(route.stages),
                "starts_with_planning": route.starts_with_planning,
                "can_dispatch": True,
                "dispatch_block_reason": "",
                "stages": [
                    {
                        "sequence": stage.sequence,
                        "stage_type": stage.stage_type,
                        "department": stage.department_label,
                        "operational_role": stage.operational_role,
                        "is_planning_stage": stage.is_planning_stage,
                    }
                    for stage in route.stages
                ],
            }
        )
    return {
        "default_path": (
            configured_default
            if configured_default in available_names
            else routes[0].name
        ),
        "paths": path_rows,
        "workers": {
            route.name: repository.get_users_for_role(route.first_stage.operational_role)
            for route in routes
        },
    }


def get_revert_targets(
    repository: ShopFloorQueryPort,
    order_name: str,
) -> list[dict[str, Any]]:
    order = repository.get_order(order_name)
    _assert_query_action(repository, order, Capability.REVERT_DEPARTMENT)
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in repository.list_revert_stages(order_name):
        stage_type = str(_value(row, "stage_type") or "")
        if _value(row, "piece_label") or stage_type in seen:
            continue
        seen.add(stage_type)
        targets.append(
            {
                "name": _value(row, "name"),
                "stage_type": stage_type,
                "label": _value(row, "department_label")
                or department_for_stage_type(stage_type)
                or stage_type,
                "status": _value(row, "status"),
                "sequence": _value(row, "sequence"),
                "assigned_to": _value(row, "assigned_to"),
            }
        )
    return targets


def _active_stage_snapshot(
    repository: ShopFloorQueryPort,
    order: Any,
    document_capabilities: frozenset[str],
) -> dict[str, Any]:
    stage_name = _value(order, "current_production_stage")
    stage = repository.get_stage_summary(str(stage_name)) if stage_name else None
    actions = build_production_action_context(
        capabilities=document_capabilities,
        facts=_production_facts(repository, order, stage),
    )
    if not stage:
        return {
            "active_stage_name": stage_name,
            "active_stage_status": None,
            "active_stage_type": None,
            "active_stage_assigned_to": None,
            "active_stage_operational_role": None,
            "actor_holds_operational_role": False,
            "can_start_stage": False,
            "can_handoff_stage": False,
            "can_reassign_worker": False,
            "can_handoff_to": None,
            "handoff_block_code": "",
            "handoff_block_reason": "",
            "route_stages": [],
            "production_actions": actions,
        }

    stage_status = str(_value(stage, "status") or "")
    stage_type = str(_value(stage, "stage_type") or "")
    operational_role = _resolve_operational_role(repository, order, stage) or ""
    actor_holds_role = decide_stage_scoped_mutation(
        actor_roles=repository.actor_roles(),
        operational_role=operational_role or None,
        has_current_stage=True,
        is_admin=repository.current_user() == "Administrator",
    )[0]
    production_path = _value(order, "production_path")
    can_handoff_to = None
    route = _production_route(repository, str(production_path or ""))
    route_stages = [
        {
            "stage_type": route_stage.stage_type,
            "department": route_stage.department_label,
            "operational_role": route_stage.operational_role,
            "sequence": route_stage.sequence,
            "is_planning_stage": route_stage.is_planning_stage,
        }
        for route_stage in (route.stages if route else ())
    ]
    if route:
        try:
            next_stage = route.next_stage(stage_type)
            can_handoff_to = next_stage.stage_type if next_stage else None
        except ValueError:
            can_handoff_to = None
    handoff_code, handoff_reason = _planning_handoff_block(route, order, stage_type)
    can_handoff = _handoff_visibility(actions, handoff_code)
    return {
        "active_stage_name": _value(stage, "name"),
        "active_stage_status": stage_status,
        "active_stage_type": stage_type,
        "active_stage_assigned_to": _value(stage, "assigned_to"),
        "active_stage_operational_role": operational_role or None,
        "actor_holds_operational_role": bool(actor_holds_role),
        "can_start_stage": bool(actions[Capability.START_ASSIGNED_STAGE]["allowed"]),
        "can_handoff_stage": can_handoff,
        "can_reassign_worker": bool(actions[Capability.REASSIGN_WORKER]["allowed"]),
        "can_handoff_to": can_handoff_to,
        "handoff_block_code": handoff_code or "",
        "handoff_block_reason": handoff_reason,
        "route_stages": route_stages,
        "production_actions": actions,
    }


def get_current_stage_context(
    repository: ShopFloorQueryPort,
    order_name: str,
) -> dict[str, Any]:
    """Return the minimal server-authorized stage context used by order actions."""

    _assert_shop_floor_access(repository)
    order = repository.get_order(order_name)
    if not repository.can_view_order(order):
        raise ShopFloorPermissionDenied("لا تملك صلاحية عرض طلب الإنتاج هذا.")
    capabilities = repository.capabilities_for_order(order)
    return _active_stage_snapshot(repository, order, capabilities)


def _plan_snapshots(
    repository: ShopFloorQueryPort,
    order: Any,
    *,
    document_capabilities: frozenset[str],
) -> dict[str, Any]:
    approved_plan = _value(order, "approved_plan")
    approved_source = str(_value(order, "approved_plan_source") or "System")
    can_system = Capability.VIEW_SYSTEM_CUTTING_PLAN in document_capabilities
    can_uploaded = Capability.VIEW_UPLOADED_CUTTING_PLAN in document_capabilities
    can_approved = Capability.VIEW_APPROVED_CUTTING_PLAN in document_capabilities
    can_view_plan = (
        Capability.VIEW_CUTTING_PLAN in document_capabilities
        or can_system
        or can_uploaded
        or can_approved
    )
    if not can_view_plan:
        return {
            "system_snapshot": {},
            "custom_snapshot": {},
            "approved_snapshot": {},
            "active_snapshot": {},
            "visible_plan_tabs": [],
            "show_dual_tabs": False,
            "approved_plan_source": approved_source,
            "active_plan_source": approved_source,
        }

    system_snapshot = (
        repository.load_plan_snapshot(order, "System") if can_system else {}
    )
    custom_snapshot = (
        repository.load_plan_snapshot(order, "Custom") if can_uploaded else {}
    )
    approved_snapshot = (
        repository.load_plan_snapshot(order) if can_approved else {}
    )

    visible_plan_tabs: list[str] = []
    if can_system:
        visible_plan_tabs.append("System")
    if can_uploaded:
        visible_plan_tabs.append("Custom")
    if can_approved:
        visible_plan_tabs.append("Approved")

    if can_approved and approved_plan:
        active_source = "Approved"
        active_snapshot = approved_snapshot
    elif (
        can_uploaded
        and approved_source == "Custom"
        and custom_snapshot.get("sheets")
    ):
        active_source = "Custom"
        active_snapshot = custom_snapshot
    elif can_system:
        active_source = "System"
        active_snapshot = system_snapshot
    elif visible_plan_tabs:
        active_source = visible_plan_tabs[0]
        active_snapshot = {
            "System": system_snapshot,
            "Custom": custom_snapshot,
            "Approved": approved_snapshot,
        }.get(active_source, {})
    else:
        active_source = approved_source
        active_snapshot = repository.load_plan_snapshot(order)

    return {
        "system_snapshot": system_snapshot,
        "custom_snapshot": custom_snapshot,
        "approved_snapshot": approved_snapshot,
        "active_snapshot": active_snapshot,
        "visible_plan_tabs": visible_plan_tabs,
        "show_dual_tabs": len(visible_plan_tabs) > 1,
        "approved_plan_source": approved_source,
        "active_plan_source": active_source,
    }


def get_order_detail(
    repository: ShopFloorQueryPort,
    order_name: str,
) -> dict[str, Any]:
    _assert_shop_floor_access(repository)
    order = repository.get_order(order_name)
    if not repository.can_view_order(order):
        raise ShopFloorPermissionDenied("لا تملك صلاحية عرض هذا الطلب.")

    document_capabilities = repository.capabilities_for_order(order)
    stages = [
        row
        for row in repository.list_order_stages(order_name)
        if not _value(row, "piece_label")
    ]
    stage_snapshot = _active_stage_snapshot(repository, order, document_capabilities)
    plan_payload = _plan_snapshots(
        repository,
        order,
        document_capabilities=document_capabilities,
    )
    can_view_plan = bool(plan_payload["visible_plan_tabs"]) or (
        Capability.VIEW_CUTTING_PLAN in document_capabilities
    )

    approved_plan = _value(order, "approved_plan")
    current_stage_type = str(stage_snapshot.get("active_stage_type") or "")
    route = _production_route(repository, str(_value(order, "production_path") or ""))
    planning_stage_active = False
    if route and current_stage_type:
        try:
            planning_stage_active = route.stage(current_stage_type).is_planning_stage
        except ValueError:
            planning_stage_active = False
    elif _value(order, "status") == "At Drawing":
        # Transitional fallback for a legacy order that has not yet been migrated
        # to an explicit Production Routing snapshot.
        planning_stage_active = True

    can_recalculate = bool(
        can_view_plan
        and Capability.RECALCULATE_PLAN in document_capabilities
        and not approved_plan
        and planning_stage_active
        and stage_snapshot.get("actor_holds_operational_role")
    )

    return {
        "order": order,
        "stages": stages,
        "stage_snapshot": stage_snapshot,
        "system_snapshot": plan_payload["system_snapshot"],
        "custom_snapshot": plan_payload["custom_snapshot"],
        "approved_snapshot": plan_payload["approved_snapshot"],
        "active_snapshot": plan_payload["active_snapshot"],
        "approved_plan_source": plan_payload["approved_plan_source"],
        "active_plan_source": plan_payload["active_plan_source"],
        "visible_plan_tabs": plan_payload["visible_plan_tabs"],
        "show_dual_tabs": plan_payload["show_dual_tabs"],
        "can_recalculate_drawing_plan": can_recalculate,
        "document_capabilities": {
            capability: capability in document_capabilities
            for capability in sorted(SHOP_FLOOR_DETAIL_CAPABILITIES)
        },
    }


__all__ = [
    "SHOP_FLOOR_DETAIL_CAPABILITIES",
    "ShopFloorPermissionDenied",
    "ShopFloorQueryError",
    "ShopFloorQueryPort",
    "get_dispatch_options",
    "get_current_stage_context",
    "get_my_archive",
    "get_my_inbox",
    "get_order_detail",
    "get_revert_targets",
    "get_shop_floor_context",
]
