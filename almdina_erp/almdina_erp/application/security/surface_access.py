from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
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
    PLAN_ARCHIVE = "plan_archive"
    FACTORY_MASTER_DATA = "factory_master_data"
    PRODUCTION_ROUTINGS = "production_routings"
    EDGE_BANDING_TYPES = "edge_banding_types"
    FACTORY_SETTINGS = "factory_settings"
    WORKFORCE = "workforce"
    PERMISSIONS = "permissions"
    ROLE_ADMIN = "role_admin"


ALL_SURFACES = frozenset(
    {
        Surface.ORDERS,
        Surface.CUSTOMER_ADMIN,
        Surface.CUTTING_PLANS,
        Surface.PRODUCTION_STAGES,
        Surface.PLAN_ARCHIVE,
        Surface.FACTORY_MASTER_DATA,
        Surface.PRODUCTION_ROUTINGS,
        Surface.EDGE_BANDING_TYPES,
        Surface.FACTORY_SETTINGS,
        Surface.WORKFORCE,
        Surface.PERMISSIONS,
        Surface.ROLE_ADMIN,
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
    can_open_master_data = bool(granted.intersection(MASTER_DATA_CAPABILITIES))

    flags = {
        Surface.ORDERS: Capability.VIEW_ORDERS in granted,
        Surface.CUSTOMER_ADMIN: (
            can_open_master_data and Capability.VIEW_CUSTOMERS in granted
        ),
        Surface.CUTTING_PLANS: Capability.VIEW_CUTTING_PLAN in granted,
        Surface.PRODUCTION_STAGES: sections.get("production") is True,
        Surface.PLAN_ARCHIVE: Capability.ARCHIVE_APPROVED_PLAN in granted,
        # The factory-master-data Page is the Production Routing console. Edge
        # types and customers have their own DocType surfaces, so granting either
        # must not advertise a routing page that will reject the user on load.
        Surface.FACTORY_MASTER_DATA: (
            can_open_master_data and Capability.VIEW_PRODUCTION_ROUTINGS in granted
        ),
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
    }
    return {surface: flags.get(surface, False) for surface in sorted(ALL_SURFACES)}


SURFACE_ROUTE_HINTS = MappingProxyType(
    {
        Surface.ORDERS: ("door-cutting-order",),
        Surface.CUSTOMER_ADMIN: ("customer",),
        Surface.CUTTING_PLANS: ("cutting-plan",),
        Surface.PRODUCTION_STAGES: ("production-stage",),
        Surface.PLAN_ARCHIVE: ("factory-plan-archive",),
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
    }
)


__all__ = [
    "ALL_SURFACES",
    "SURFACE_ROUTE_HINTS",
    "Surface",
    "build_surface_access",
]
