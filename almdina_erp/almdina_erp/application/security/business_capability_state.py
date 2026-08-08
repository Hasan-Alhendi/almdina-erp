from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CAPABILITY_PRESENTATION,
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
    normalize_capabilities,
)


_EDGE_ADMIN_ACTIONS = frozenset(
    {
        Capability.CREATE_EDGE_BANDING_TYPES,
        Capability.EDIT_EDGE_BANDING_TYPES,
        Capability.DELETE_EDGE_BANDING_TYPES,
    }
)
_DRAWING_VIEW_ACTIONS = frozenset(
    {
        Capability.EDIT_SPECIAL_DRAWING,
        Capability.EXPORT_DXF,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
    }
)


def normalize_business_capability_state(
    raw: Mapping[str, Any] | None,
) -> dict[str, bool]:
    """Normalize explicit business authority without promoting technical grants.

    Order entry needs Customer and Edge Banding Type records as lookup data, but
    that technical dependency must not become a business grant that exposes the
    corresponding administration surfaces.

    ``approve_dxf`` is retained as the historical storage key for compatibility,
    but its business meaning is approval of the selected production cutting plan.
    It therefore implies cutting-plan viewing, not access to the drawing workspace.
    Upload/replace/export/special-drawing actions still imply drawing visibility.
    """

    supplied = {str(key): value for key, value in dict(raw or {}).items()}
    normalized = normalize_capability_state(supplied)

    normalized[Capability.VIEW_CUSTOMERS] = (
        supplied.get(Capability.VIEW_CUSTOMERS) is True
    )
    normalized[Capability.VIEW_EDGE_BANDING_TYPES] = (
        supplied.get(Capability.VIEW_EDGE_BANDING_TYPES) is True
        or any(supplied.get(capability) is True for capability in _EDGE_ADMIN_ACTIONS)
    )

    # Plan approval is a planning authority. The old low-level key is preserved
    # to avoid a destructive permission migration, while the effective business
    # dependencies now match what the user is actually allowed to do.
    if supplied.get(Capability.APPROVE_DXF) is True:
        normalized[Capability.VIEW_CUTTING_PLAN] = True
    normalized[Capability.VIEW_DRAWING_WORKSPACE] = (
        supplied.get(Capability.VIEW_DRAWING_WORKSPACE) is True
        or any(supplied.get(capability) is True for capability in _DRAWING_VIEW_ACTIONS)
    )
    return normalized


def enabled_business_capabilities(
    raw: Mapping[str, Any] | None,
) -> frozenset[str]:
    state = normalize_business_capability_state(raw)
    return normalize_capabilities(
        capability
        for capability, enabled in state.items()
        if enabled is True
    )


def changed_business_capabilities(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    old = normalize_business_capability_state(before)
    new = normalize_business_capability_state(after)
    changes: list[dict[str, Any]] = []
    for capability in sorted(ALL_CAPABILITIES):
        if old[capability] == new[capability]:
            continue
        presentation = CAPABILITY_PRESENTATION[capability]
        changes.append(
            {
                "key": capability,
                "label": presentation["label"],
                "risk": presentation["risk"],
                "before": old[capability],
                "after": new[capability],
            }
        )
    return changes


def business_permission_impact(
    raw: Mapping[str, Any] | None,
) -> dict[str, Any]:
    granted = enabled_business_capabilities(raw)
    critical = sorted(
        capability
        for capability in granted
        if CAPABILITY_PRESENTATION[capability]["risk"] == "critical"
    )
    return {
        "enabled_count": len(granted),
        "critical_count": len(critical),
        "critical_capabilities": critical,
        "navigation": build_navigation_context(granted),
    }


__all__ = [
    "business_permission_impact",
    "changed_business_capabilities",
    "enabled_business_capabilities",
    "normalize_business_capability_state",
]
