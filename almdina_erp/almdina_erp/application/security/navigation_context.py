from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import (
    ADMINISTRATION_CAPABILITIES,
    CONTROL_CENTER_CAPABILITIES,
    COSTING_CAPABILITIES,
    DRAWING_CAPABILITIES,
    ORDER_CAPABILITIES,
    PLANNING_CAPABILITIES,
    PRODUCTION_CAPABILITIES,
    PRODUCTION_OPERATOR_CAPABILITIES,
    PRODUCTION_SUPERVISOR_CAPABILITIES,
    REPORTING_CAPABILITIES,
    SHOP_FLOOR_ACCESS_CAPABILITIES,
    Capability,
    normalize_capabilities,
)


WORKSPACE_MAIN = "Almdina ERP"
WORKSPACE_SHOP_FLOOR = "Shop Floor"
WORKSPACE_CONTROL_CENTER = "Almdina Control Center"
WORKSPACE_REPORTS = "Almdina Reports"
WORKSPACE_SETTINGS = "Almdina Settings"
WORKSPACE_GO_LIVE = "Almdina Go-Live"

_FINANCIAL_CAPABILITIES = frozenset(
    COSTING_CAPABILITIES.difference({Capability.PRINT_MEASUREMENTS})
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


def _intersects(granted: frozenset[str], requested: Iterable[str]) -> bool:
    return bool(granted.intersection(requested))


def _profile(granted: frozenset[str]) -> str:
    """Return a compatibility profile derived only from capabilities."""

    if not granted:
        return "shared"

    broad = frozenset(
        _ORDER_MANAGEMENT_CAPABILITIES
        | _FINANCIAL_CAPABILITIES
        | _CONTROL_CENTER_MANAGEMENT_CAPABILITIES
        | REPORTING_CAPABILITIES
        | PRODUCTION_SUPERVISOR_CAPABILITIES
        | ADMINISTRATION_CAPABILITIES
    )
    if _intersects(granted, PRODUCTION_OPERATOR_CAPABILITIES) and not _intersects(
        granted,
        broad,
    ):
        return "shop_floor"

    order_entry_actions = frozenset(
        {
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.SUBMIT_ORDER,
            Capability.PRINT_MEASUREMENTS,
        }
    )
    if _intersects(granted, order_entry_actions) and not _intersects(
        granted,
        _FINANCIAL_CAPABILITIES
        | PLANNING_CAPABILITIES
        | DRAWING_CAPABILITIES
        | PRODUCTION_CAPABILITIES
        | CONTROL_CENTER_CAPABILITIES
        | REPORTING_CAPABILITIES
        | ADMINISTRATION_CAPABILITIES,
    ):
        return "order_entry"

    return "full"


def build_navigation_context(
    granted_capabilities: Iterable[str] | None,
) -> dict[str, Any]:
    """Build the shared Almdina shell navigation from business capabilities.

    The same Desk shell is retained for every authorized Almdina user.
    Capabilities select the useful workspaces, home destination and visible
    sections. Users without Almdina grants are left on their existing Desk and
    application navigation.
    """

    granted = normalize_capabilities(granted_capabilities)
    active = bool(granted)
    has_orders = _intersects(granted, ORDER_CAPABILITIES)
    has_costing = _intersects(granted, _FINANCIAL_CAPABILITIES)
    has_planning = _intersects(granted, PLANNING_CAPABILITIES)
    has_drawing = _intersects(granted, DRAWING_CAPABILITIES)
    has_production = _intersects(granted, PRODUCTION_CAPABILITIES)
    has_quality = _intersects(granted, CONTROL_CENTER_CAPABILITIES)
    has_reports = _intersects(granted, REPORTING_CAPABILITIES)
    has_supervision = _intersects(granted, PRODUCTION_SUPERVISOR_CAPABILITIES)
    has_administration = _intersects(granted, ADMINISTRATION_CAPABILITIES)
    has_shop_floor = _intersects(granted, SHOP_FLOOR_ACCESS_CAPABILITIES)
    has_control_center = (
        has_quality
        or has_supervision
        or Capability.APPROVE_DXF in granted
        or has_administration
    )

    operator_only = active and _intersects(
        granted,
        PRODUCTION_OPERATOR_CAPABILITIES,
    ) and not _intersects(
        granted,
        _ORDER_MANAGEMENT_CAPABILITIES
        | _FINANCIAL_CAPABILITIES
        | _CONTROL_CENTER_MANAGEMENT_CAPABILITIES
        | REPORTING_CAPABILITIES
        | PRODUCTION_SUPERVISOR_CAPABILITIES
        | ADMINISTRATION_CAPABILITIES,
    )

    workspaces: list[str] = []
    if operator_only:
        workspaces.append(WORKSPACE_SHOP_FLOOR)
    elif active:
        workspaces.append(WORKSPACE_MAIN)
        if has_shop_floor:
            workspaces.append(WORKSPACE_SHOP_FLOOR)
        if has_control_center:
            workspaces.append(WORKSPACE_CONTROL_CENTER)
        if has_reports or has_administration:
            workspaces.append(WORKSPACE_REPORTS)
        if (
            Capability.EDIT_COST_SETTINGS in granted
            or Capability.MANAGE_FACTORY_SETTINGS in granted
            or Capability.MANAGE_USERS in granted
            or Capability.MANAGE_PERMISSIONS in granted
        ):
            workspaces.append(WORKSPACE_SETTINGS)
        if has_administration:
            workspaces.append(WORKSPACE_GO_LIVE)

    home_page = "shop-floor-inbox" if operator_only else "almdina-erp"

    return {
        "shared_shell": active,
        "app_only": active,
        "profile": _profile(granted),
        "home_page": home_page if active else "",
        "default_route": f"/app/{home_page}" if active else "",
        "workspaces": workspaces,
        "sections": {
            "orders": has_orders,
            "costing": has_costing,
            "planning": has_planning,
            "drawing": has_drawing,
            "production": has_production,
            "quality": has_quality,
            "administration": has_administration,
            "reports": has_reports,
        },
    }


__all__ = [
    "WORKSPACE_CONTROL_CENTER",
    "WORKSPACE_GO_LIVE",
    "WORKSPACE_MAIN",
    "WORKSPACE_REPORTS",
    "WORKSPACE_SETTINGS",
    "WORKSPACE_SHOP_FLOOR",
    "build_navigation_context",
]
