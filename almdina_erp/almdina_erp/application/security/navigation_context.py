from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almdina_erp.almdina_erp.application.security.report_access import (
    build_report_access,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CONTROL_CENTER_CAPABILITIES,
    COSTING_CAPABILITIES,
    DRAWING_CAPABILITIES,
    FACTORY_SETTINGS_CAPABILITIES,
    MASTER_DATA_CAPABILITIES,
    ORDER_CAPABILITIES,
    PLANNING_CAPABILITIES,
    PRODUCTION_CAPABILITIES,
    PRODUCTION_OPERATOR_CAPABILITIES,
    PRODUCTION_SUPERVISOR_CAPABILITIES,
    REPORTING_CAPABILITIES,
    SHOP_FLOOR_ACCESS_CAPABILITIES,
    WORKFORCE_CAPABILITIES,
    Capability,
    normalize_capabilities,
)


DESKTOP_PAGE_ROUTE = "desktop"
WORKSPACE_MAIN = "Almdina ERP"
WORKSPACE_MAIN_ROUTE = "almdina-erp"
WORKSPACE_SHOP_FLOOR = "Shop Floor"
WORKSPACE_CONTROL_CENTER = "Almdina Control Center"
WORKSPACE_REPORTS = "Almdina Reports"
WORKSPACE_SETTINGS = "Almdina Settings"
WORKSPACE_GO_LIVE = "Almdina Go-Live"
ORDER_LIST_ROUTE = "door-cutting-order"

_CUSTOMER_DOCUMENT_CAPABILITIES = frozenset(
    {Capability.PRINT_MEASUREMENTS, Capability.PRINT_CUSTOMER_INVOICE}
)
_FINANCIAL_CAPABILITIES = frozenset(
    COSTING_CAPABILITIES.difference(_CUSTOMER_DOCUMENT_CAPABILITIES)
)
_ORDER_MANAGEMENT_CAPABILITIES = frozenset(
    ORDER_CAPABILITIES.difference({Capability.VIEW_ORDERS})
)
_CONTROL_CENTER_OPERATOR_CAPABILITIES = frozenset(
    {
        Capability.RECORD_INCIDENT,
        Capability.VIEW_REPLACEMENTS,
        Capability.START_REPLACEMENT,
        Capability.COMPLETE_REPLACEMENT,
    }
)
_CONTROL_CENTER_MANAGEMENT_CAPABILITIES = frozenset(
    CONTROL_CENTER_CAPABILITIES.difference(_CONTROL_CENTER_OPERATOR_CAPABILITIES)
)
_CONFIGURATION_CAPABILITIES = frozenset(
    FACTORY_SETTINGS_CAPABILITIES | MASTER_DATA_CAPABILITIES
)

# ``approve_dxf`` is retained as a persisted compatibility key, but it now
# represents approval of the selected production cutting plan. Navigation must
# therefore treat it as planning authority and never as implicit drawing/control
# center access.
_PLAN_APPROVAL_CAPABILITIES = frozenset({Capability.APPROVE_DXF})
_PLANNING_NAV_CAPABILITIES = frozenset(
    PLANNING_CAPABILITIES | _PLAN_APPROVAL_CAPABILITIES
)
_DRAWING_NAV_CAPABILITIES = frozenset(
    DRAWING_CAPABILITIES.difference(_PLAN_APPROVAL_CAPABILITIES)
)
_CONTROL_CENTER_NAV_CAPABILITIES = frozenset(
    CONTROL_CENTER_CAPABILITIES.difference(_PLAN_APPROVAL_CAPABILITIES)
)


def _intersects(granted: frozenset[str], requested: Iterable[str]) -> bool:
    return bool(granted.intersection(requested))


def _visible_configuration_capabilities(granted: frozenset[str]) -> frozenset[str]:
    """Return explicit business configuration grants only.

    Order-entry Customer/Edge lookup dependencies no longer live in canonical
    business state, so every master-data capability present here is explicit and
    may safely influence navigation visibility.
    """

    return frozenset(granted.intersection(_CONFIGURATION_CAPABILITIES))


def _profile(granted: frozenset[str]) -> str:
    if not granted:
        return "shared"
    visible_configuration = _visible_configuration_capabilities(granted)
    broad = frozenset(
        _ORDER_MANAGEMENT_CAPABILITIES
        | _FINANCIAL_CAPABILITIES
        | _CONTROL_CENTER_MANAGEMENT_CAPABILITIES
        | REPORTING_CAPABILITIES
        | PRODUCTION_SUPERVISOR_CAPABILITIES
        | WORKFORCE_CAPABILITIES
        | visible_configuration
        | frozenset({Capability.MANAGE_PERMISSIONS})
    )
    if _intersects(granted, PRODUCTION_OPERATOR_CAPABILITIES) and not _intersects(
        granted, broad
    ):
        return "shop_floor"
    order_entry_actions = frozenset(
        {
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.SUBMIT_ORDER,
            Capability.PRINT_MEASUREMENTS,
            Capability.PRINT_CUSTOMER_INVOICE,
        }
    )
    if _intersects(granted, order_entry_actions) and not _intersects(
        granted,
        _FINANCIAL_CAPABILITIES
        | _PLANNING_NAV_CAPABILITIES
        | _DRAWING_NAV_CAPABILITIES
        | PRODUCTION_CAPABILITIES
        | _CONTROL_CENTER_NAV_CAPABILITIES
        | REPORTING_CAPABILITIES
        | WORKFORCE_CAPABILITIES
        | visible_configuration
        | frozenset({Capability.MANAGE_PERMISSIONS}),
    ):
        return "order_entry"
    return "full"


def build_navigation_context(
    granted_capabilities: Iterable[str] | None,
    *,
    system_administrator: bool = False,
) -> dict[str, Any]:
    granted = normalize_capabilities(granted_capabilities)
    active = bool(granted) or system_administrator
    has_orders = _intersects(granted, ORDER_CAPABILITIES)
    has_costing = _intersects(granted, _FINANCIAL_CAPABILITIES)
    has_planning = _intersects(granted, _PLANNING_NAV_CAPABILITIES)
    has_drawing = _intersects(granted, _DRAWING_NAV_CAPABILITIES)
    has_production = _intersects(granted, PRODUCTION_CAPABILITIES)
    has_quality = _intersects(granted, _CONTROL_CENTER_NAV_CAPABILITIES)
    report_access = build_report_access(granted)
    # Every current Almdina Script Report is registered against Door Cutting
    # Order. Without VIEW_ORDERS Frappe rejects the report before execute(), so
    # the workspace must not advertise an action the user cannot open.
    has_reports = report_access.operational and Capability.VIEW_ORDERS in granted
    has_workforce = _intersects(granted, WORKFORCE_CAPABILITIES)
    has_factory_settings = _intersects(granted, FACTORY_SETTINGS_CAPABILITIES)
    visible_configuration = _visible_configuration_capabilities(granted)
    has_master_data = _intersects(visible_configuration, MASTER_DATA_CAPABILITIES)
    has_permissions_admin = Capability.MANAGE_PERMISSIONS in granted
    has_supervision = _intersects(granted, PRODUCTION_SUPERVISOR_CAPABILITIES)
    has_shop_floor = _intersects(granted, SHOP_FLOOR_ACCESS_CAPABILITIES)
    has_control_center = has_quality or has_supervision or has_permissions_admin

    operator_only = (
        active
        and not system_administrator
        and _intersects(granted, PRODUCTION_OPERATOR_CAPABILITIES)
        and not _intersects(
            granted,
            _ORDER_MANAGEMENT_CAPABILITIES
            | _FINANCIAL_CAPABILITIES
            | _CONTROL_CENTER_MANAGEMENT_CAPABILITIES
            | REPORTING_CAPABILITIES
            | PRODUCTION_SUPERVISOR_CAPABILITIES
            | WORKFORCE_CAPABILITIES
            | visible_configuration
            | frozenset({Capability.MANAGE_PERMISSIONS}),
        )
    )

    workspaces: list[str] = []
    if operator_only:
        # Operators use the same primary workspace and order list as admins;
        # server-side scope changes the rows, never the interface.
        workspaces.append(WORKSPACE_MAIN)
    elif active:
        workspaces.append(WORKSPACE_MAIN)
        if has_shop_floor:
            workspaces.append(WORKSPACE_SHOP_FLOOR)
        if has_control_center:
            workspaces.append(WORKSPACE_CONTROL_CENTER)
        if has_reports or has_permissions_admin:
            workspaces.append(WORKSPACE_REPORTS)
        if (
            Capability.EDIT_COST_SETTINGS in granted
            or has_workforce
            or has_factory_settings
            or has_master_data
            or has_permissions_admin
        ):
            workspaces.append(WORKSPACE_SETTINGS)
        if has_permissions_admin:
            workspaces.append(WORKSPACE_GO_LIVE)

    return {
        "shared_shell": active,
        "app_only": active and not system_administrator,
        "profile": _profile(granted),
        "workspaces": workspaces,
        "sections": {
            "orders": has_orders,
            "costing": has_costing,
            "planning": has_planning,
            "drawing": has_drawing,
            "production": has_production,
            "quality": has_quality,
            "workforce": has_workforce,
            "factory_settings": has_factory_settings,
            "master_data": has_master_data,
            "administration": has_permissions_admin,
            "reports": has_reports,
        },
    }


__all__ = [
    "DESKTOP_PAGE_ROUTE",
    "ORDER_LIST_ROUTE",
    "WORKSPACE_CONTROL_CENTER",
    "WORKSPACE_GO_LIVE",
    "WORKSPACE_MAIN",
    "WORKSPACE_MAIN_ROUTE",
    "WORKSPACE_REPORTS",
    "WORKSPACE_SETTINGS",
    "WORKSPACE_SHOP_FLOOR",
    "build_navigation_context",
]
