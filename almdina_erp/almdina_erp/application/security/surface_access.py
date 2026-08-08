from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.report_access import (
    build_report_access,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    MASTER_DATA_CAPABILITIES,
    Capability,
    normalize_capabilities,
)


class Surface:
    """Stable UI surface keys shared by server permission context and Desk."""

    ORDERS = "orders"
    CUSTOMER_ADMIN = "customer_admin"
    CUTTING_PLANS = "cutting_plans"
    PRODUCTION_STAGES = "production_stages"
    PRODUCTION_INCIDENTS = "production_incidents"
    REPLACEMENTS = "replacements"
    FACTORY_MASTER_DATA = "factory_master_data"
    PRODUCTION_ROUTINGS = "production_routings"
    EDGE_BANDING_TYPES = "edge_banding_types"
    FACTORY_SETTINGS = "factory_settings"
    WORKFORCE = "workforce"
    PERMISSIONS = "permissions"
    ROLE_ADMIN = "role_admin"
    REPORTS_WORKSPACE = "reports_workspace"
    REPORT_FACTORY_OPERATIONS_SUMMARY = "report_factory_operations_summary"
    REPORT_FACTORY_ORDER_ANALYSIS = "report_factory_order_analysis"
    REPORT_PRODUCTION_STAGE_PERFORMANCE = "report_production_stage_performance"
    REPORT_PRODUCTION_INCIDENTS = "report_production_incidents_and_replacements"
    REPORT_BOARD_USAGE = "report_board_usage_analysis"
    REPORT_PIECE_SIZE_USAGE = "report_piece_size_usage_analysis"
    REPORT_ORDER_STOCK_AVAILABILITY = "report_order_stock_availability"
    REPORT_REMNANT_INVENTORY = "report_remnant_inventory"


REPORT_SURFACES = frozenset(
    {
        Surface.REPORT_FACTORY_OPERATIONS_SUMMARY,
        Surface.REPORT_FACTORY_ORDER_ANALYSIS,
        Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE,
        Surface.REPORT_PRODUCTION_INCIDENTS,
        Surface.REPORT_BOARD_USAGE,
        Surface.REPORT_PIECE_SIZE_USAGE,
        Surface.REPORT_ORDER_STOCK_AVAILABILITY,
        Surface.REPORT_REMNANT_INVENTORY,
    }
)
FINANCIAL_REPORT_SURFACES = frozenset({Surface.REPORT_FACTORY_ORDER_ANALYSIS})
OPERATIONAL_REPORT_SURFACES = REPORT_SURFACES.difference(FINANCIAL_REPORT_SURFACES)

ALL_SURFACES = frozenset(
    {
        Surface.ORDERS,
        Surface.CUSTOMER_ADMIN,
        Surface.CUTTING_PLANS,
        Surface.PRODUCTION_STAGES,
        Surface.PRODUCTION_INCIDENTS,
        Surface.REPLACEMENTS,
        Surface.FACTORY_MASTER_DATA,
        Surface.PRODUCTION_ROUTINGS,
        Surface.EDGE_BANDING_TYPES,
        Surface.FACTORY_SETTINGS,
        Surface.WORKFORCE,
        Surface.PERMISSIONS,
        Surface.ROLE_ADMIN,
        Surface.REPORTS_WORKSPACE,
        *REPORT_SURFACES,
    }
)


def build_surface_access(
    granted_capabilities: Iterable[str] | None,
    *,
    system_administrator: bool = False,
) -> dict[str, bool]:
    """Return exact visibility/access flags for Almdina Desk surfaces.

    Business capability state already excludes lookup-only Customer/Edge grants
    derived from order entry. Therefore an explicit master-data view grant can
    safely expose its administration surface, while order-entry lookup support
    remains invisible.
    """

    if system_administrator:
        return {surface: True for surface in sorted(ALL_SURFACES)}

    granted = normalize_capabilities(granted_capabilities)
    navigation = build_navigation_context(granted)
    sections = navigation["sections"]
    report_access = build_report_access(granted)

    can_open_operational_reports = (
        report_access.operational and Capability.VIEW_ORDERS in granted
    )
    can_open_financial_reports = (
        report_access.financial and Capability.VIEW_ORDERS in granted
    )
    can_open_master_data = bool(granted.intersection(MASTER_DATA_CAPABILITIES))

    flags = {
        Surface.ORDERS: Capability.VIEW_ORDERS in granted,
        Surface.CUSTOMER_ADMIN: (
            can_open_master_data and Capability.VIEW_CUSTOMERS in granted
        ),
        Surface.CUTTING_PLANS: Capability.VIEW_CUTTING_PLAN in granted,
        Surface.PRODUCTION_STAGES: sections.get("production") is True,
        Surface.PRODUCTION_INCIDENTS: Capability.VIEW_PRODUCTION_INCIDENTS in granted,
        Surface.REPLACEMENTS: Capability.VIEW_REPLACEMENTS in granted,
        Surface.FACTORY_MASTER_DATA: can_open_master_data,
        Surface.PRODUCTION_ROUTINGS: (
            can_open_master_data and Capability.VIEW_PRODUCTION_ROUTINGS in granted
        ),
        Surface.EDGE_BANDING_TYPES: (
            can_open_master_data and Capability.VIEW_EDGE_BANDING_TYPES in granted
        ),
        Surface.FACTORY_SETTINGS: sections.get("factory_settings") is True,
        Surface.WORKFORCE: Capability.VIEW_USERS in granted,
        Surface.PERMISSIONS: Capability.MANAGE_PERMISSIONS in granted,
        Surface.ROLE_ADMIN: Capability.MANAGE_PERMISSIONS in granted,
        Surface.REPORTS_WORKSPACE: can_open_operational_reports,
    }
    for surface in OPERATIONAL_REPORT_SURFACES:
        flags[surface] = can_open_operational_reports
    for surface in FINANCIAL_REPORT_SURFACES:
        flags[surface] = can_open_financial_reports
    return {surface: flags.get(surface, False) for surface in sorted(ALL_SURFACES)}


SURFACE_ROUTE_HINTS = MappingProxyType(
    {
        Surface.ORDERS: ("door-cutting-order",),
        Surface.CUSTOMER_ADMIN: ("customer",),
        Surface.CUTTING_PLANS: ("cutting-plan",),
        Surface.PRODUCTION_STAGES: ("production-stage",),
        Surface.PRODUCTION_INCIDENTS: ("production-incident",),
        Surface.REPLACEMENTS: ("replacement-piece",),
        Surface.FACTORY_MASTER_DATA: ("factory-master-data",),
        Surface.PRODUCTION_ROUTINGS: ("production-routing",),
        Surface.EDGE_BANDING_TYPES: ("edge-banding-type",),
        Surface.FACTORY_SETTINGS: (
            "factory-production-settings",
            "almdina-erp-settings",
        ),
        Surface.WORKFORCE: ("factory-workforce",),
        Surface.PERMISSIONS: ("factory-permissions",),
        Surface.ROLE_ADMIN: (
            "role",
            "role-permission-manager",
            "permission-inspector",
            "permission-type",
            "user-permission",
            "user",
        ),
        Surface.REPORT_FACTORY_OPERATIONS_SUMMARY: ("factory-operations-summary",),
        Surface.REPORT_FACTORY_ORDER_ANALYSIS: ("factory-order-analysis",),
        Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE: ("production-stage-performance",),
        Surface.REPORT_PRODUCTION_INCIDENTS: ("production-incidents-and-replacements",),
        Surface.REPORT_BOARD_USAGE: ("board-usage-analysis",),
        Surface.REPORT_PIECE_SIZE_USAGE: ("piece-size-usage-analysis",),
        Surface.REPORT_ORDER_STOCK_AVAILABILITY: ("order-stock-availability",),
        Surface.REPORT_REMNANT_INVENTORY: ("remnant-inventory",),
    }
)


__all__ = [
    "ALL_SURFACES",
    "FINANCIAL_REPORT_SURFACES",
    "OPERATIONAL_REPORT_SURFACES",
    "REPORT_SURFACES",
    "SURFACE_ROUTE_HINTS",
    "Surface",
    "build_surface_access",
]
