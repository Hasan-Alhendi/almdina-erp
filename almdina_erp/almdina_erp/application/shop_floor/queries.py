from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    SHOP_FLOOR_STAGE_TYPES,
    department_for_stage_type,
    department_status_for_stage_status,
    next_stage_type,
)
from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    build_production_action_context,
    decide_production_action,
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


class ShopFloorQueryError(ValueError):
    """Raised when a shop-floor read use case cannot be completed."""


class ShopFloorPermissionDenied(PermissionError):
    """Raised when the current user cannot view shop-floor data."""


class ShopFloorQueryPort(Protocol):
    def current_user(self) -> str: ...

    def session_identity(self) -> dict[str, Any]: ...

    def global_capabilities(self) -> frozenset[str]: ...

    def is_admin(self) -> bool: ...

    def capabilities_for_order(self, order: Any) -> frozenset[str]: ...

    def list_inbox_stages(self, *, user: str, is_admin: bool) -> list[Any]: ...

    def list_archive_stages(self, *, user: str, is_admin: bool) -> list[Any]: ...

    def current_stage_names(
        self,
        order_names: Sequence[str],
    ) -> Mapping[str, str | None]: ...

    def order_summaries(self, order_names: Sequence[str]) -> Mapping[str, Any]: ...

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

    def get_users_for_stage(self, stage_type: str) -> list[dict[str, str]]: ...


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
        raise ShopFloorPermissionDenied(
            "You do not have access to the production workspace."
        )
    return capabilities


def get_shop_floor_context(repository: ShopFloorQueryPort) -> dict[str, Any]:
    capabilities = _assert_shop_floor_access(repository)
    identity = dict(repository.session_identity())
    identity.pop("roles", None)
    return {
        "identity": identity,
        "navigation": build_navigation_context(capabilities),
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
        if not current_by_order.get(
            str(_value(row, "door_cutting_order") or "")
        )
        or _value(row, "name")
        == current_by_order.get(str(_value(row, "door_cutting_order") or ""))
    ]


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
    enriched: list[dict[str, Any]] = []
    for stage in stages:
        order_name = str(_value(stage, "door_cutting_order") or "")
        order = orders.get(order_name) or {}
        production_path = _value(order, "production_path")
        stage_type = str(_value(stage, "stage_type") or "")
        can_handoff_to = None
        if production_path:
            try:
                can_handoff_to = next_stage_type(
                    str(production_path),
                    stage_type,
                )
            except ValueError:
                can_handoff_to = None
        actions = build_production_action_context(
            capabilities=repository.capabilities_for_order(order),
            facts=_production_facts(repository, order, stage),
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
                or department_status_for_stage_status(
                    str(_value(stage, "status") or "")
                ),
                "approved_plan": _value(order, "approved_plan"),
                "production_dxf": _value(order, "production_dxf"),
                "drawing_dxf_status": _value(order, "drawing_dxf_status"),
                "revision": _value(order, "revision"),
                "department_label": department_for_stage_type(stage_type)
                or stage_type,
                "can_handoff_to": can_handoff_to,
                "can_start_stage": bool(
                    actions[Capability.START_ASSIGNED_STAGE]["allowed"]
                ),
                "can_handoff_stage": bool(
                    actions[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"]
                ),
            }
        )
    return enriched


def get_my_inbox(repository: ShopFloorQueryPort) -> list[dict[str, Any]]:
    _assert_shop_floor_access(repository)
    user = repository.current_user()
    stages = repository.list_inbox_stages(
        user=user,
        is_admin=repository.is_admin(),
    )
    return _enrich_stage_rows(
        repository,
        _filter_active_stages(repository, stages),
    )


def get_my_archive(repository: ShopFloorQueryPort) -> list[dict[str, Any]]:
    _assert_shop_floor_access(repository)
    user = repository.current_user()
    stages = repository.list_archive_stages(
        user=user,
        is_admin=repository.is_admin(),
    )
    return _enrich_stage_rows(repository, stages)


def _production_facts(
    repository: ShopFloorQueryPort,
    order: Any,
    stage: Any | None = None,
) -> ProductionActionFacts:
    return ProductionActionFacts(
        order_status=_value(order, "status"),
        production_path=_value(order, "production_path"),
        current_stage_name=_value(order, "current_production_stage"),
        has_cutting_plan=bool(_value(order, "cutting_plan_json")),
        plan_needs_recalculation=_as_bool(
            _value(order, "plan_needs_recalculation")
        ),
        stage_name=_value(stage, "name") if stage else None,
        stage_type=_value(stage, "stage_type") if stage else None,
        stage_status=_value(stage, "status") if stage else None,
        assigned_to=_value(stage, "assigned_to") if stage else None,
        actor=repository.current_user(),
        drawing_dxf_status=_value(order, "drawing_dxf_status"),
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
    return {
        "paths": [
            {
                "value": "Sharyoun",
                "label": "Sharyoun (simple cutting)",
                "first_stage_type": "Sharyoun",
            },
            {
                "value": "Drawing",
                "label": "Drawing → CNC",
                "first_stage_type": "Drawing",
            },
        ],
        "workers": {
            stage_type: repository.get_users_for_stage(stage_type)
            for stage_type in SHOP_FLOOR_STAGE_TYPES
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
                "label": department_for_stage_type(stage_type) or stage_type,
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
            "can_start_stage": False,
            "can_handoff_stage": False,
            "can_reassign_worker": False,
            "can_handoff_to": None,
            "production_actions": actions,
        }

    stage_status = str(_value(stage, "status") or "")
    stage_type = str(_value(stage, "stage_type") or "")
    production_path = _value(order, "production_path")
    can_handoff_to = None
    if production_path:
        try:
            can_handoff_to = next_stage_type(
                str(production_path),
                stage_type,
            )
        except ValueError:
            can_handoff_to = None
    return {
        "active_stage_name": _value(stage, "name"),
        "active_stage_status": stage_status,
        "active_stage_type": stage_type,
        "active_stage_assigned_to": _value(stage, "assigned_to"),
        "can_start_stage": bool(
            actions[Capability.START_ASSIGNED_STAGE]["allowed"]
        ),
        "can_handoff_stage": bool(
            actions[Capability.HANDOFF_ASSIGNED_STAGE]["allowed"]
        ),
        "can_reassign_worker": bool(
            actions[Capability.REASSIGN_WORKER]["allowed"]
        ),
        "can_handoff_to": can_handoff_to,
        "production_actions": actions,
    }


def _plan_snapshots(
    repository: ShopFloorQueryPort,
    order: Any,
    *,
    can_view_plan: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool, str, str]:
    approved_plan = _value(order, "approved_plan")
    approved_source = str(
        _value(order, "approved_plan_source") or "System"
    )
    if not can_view_plan:
        return {}, {}, {}, False, approved_source, approved_source

    system_snapshot = repository.load_plan_snapshot(order, "System")
    custom_snapshot = repository.load_plan_snapshot(order, "Custom")
    can_view_dual = repository.user_can_view_dual_plans()
    active_source = approved_source if can_view_dual and approved_plan else "System"
    if not can_view_dual:
        active_source = approved_source

    active_snapshot = (
        custom_snapshot
        if active_source == "Custom" and custom_snapshot.get("sheets")
        else system_snapshot
    )
    if approved_plan and not can_view_dual:
        active_snapshot = repository.load_plan_snapshot(order)

    return (
        system_snapshot,
        custom_snapshot,
        active_snapshot,
        can_view_dual,
        approved_source,
        active_source,
    )


def get_order_detail(
    repository: ShopFloorQueryPort,
    order_name: str,
) -> dict[str, Any]:
    _assert_shop_floor_access(repository)
    order = repository.get_order(order_name)
    if not repository.can_view_order(order):
        raise ShopFloorPermissionDenied("Not permitted to view this order.")

    document_capabilities = repository.capabilities_for_order(order)
    stages = [
        row
        for row in repository.list_order_stages(order_name)
        if not _value(row, "piece_label")
    ]
    stage_snapshot = _active_stage_snapshot(
        repository,
        order,
        document_capabilities,
    )
    can_view_plan = Capability.VIEW_CUTTING_PLAN in document_capabilities
    (
        system_snapshot,
        custom_snapshot,
        active_snapshot,
        can_view_dual,
        approved_source,
        active_source,
    ) = _plan_snapshots(
        repository,
        order,
        can_view_plan=can_view_plan,
    )

    approved_plan = _value(order, "approved_plan")
    current_stage_type = stage_snapshot.get("active_stage_type")
    can_recalculate = bool(
        can_view_plan
        and Capability.RECALCULATE_PLAN in document_capabilities
        and _value(order, "production_path") == "Drawing"
        and not approved_plan
        and (
            current_stage_type == "Drawing"
            or _value(order, "status") == "At Drawing"
        )
    )

    return {
        "order": order,
        "stages": stages,
        "stage_snapshot": stage_snapshot,
        "system_snapshot": system_snapshot,
        "custom_snapshot": custom_snapshot,
        "active_snapshot": active_snapshot,
        "approved_plan_source": approved_source,
        "active_plan_source": active_source,
        "show_dual_tabs": can_view_dual,
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
    "get_my_archive",
    "get_my_inbox",
    "get_order_detail",
    "get_revert_targets",
    "get_shop_floor_context",
]
