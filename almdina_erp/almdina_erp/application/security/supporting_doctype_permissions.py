from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CONTROL_CENTER_CAPABILITIES,
    PRODUCTION_CAPABILITIES,
    REPORTING_CAPABILITIES,
    Capability,
)


SUPPORTING_DOCTYPES = (
    "Cutting Plan",
    "Production Incident",
    "Production Stage",
)

_STAGE_READ_CAPABILITIES = frozenset(PRODUCTION_CAPABILITIES) | frozenset(
    {
        Capability.RECORD_INCIDENT,
        Capability.CREATE_REPLACEMENT,
        Capability.VIEW_OPERATIONAL_REPORTS,
        Capability.VIEW_FINANCIAL_REPORTS,
    }
)
_INCIDENT_READ_CAPABILITIES = frozenset(CONTROL_CENTER_CAPABILITIES) | frozenset(
    REPORTING_CAPABILITIES
)


def _any_enabled(state: Mapping[str, bool], capabilities: frozenset[str]) -> bool:
    return any(state.get(capability) is True for capability in capabilities)


def supporting_standard_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[str, bool]:
    """Project business capabilities onto native rights of related records.

    Frappe controller permission hooks can only deny an existing native grant;
    they cannot create a missing one. These projections provide the minimum
    DocPerm grant while query/has-permission hooks keep shop-floor scope narrow.
    """

    normalized = normalize_capability_state(state)
    if doctype == "Cutting Plan":
        can_read = normalized[Capability.VIEW_CUTTING_PLAN]
    elif doctype == "Production Stage":
        can_read = _any_enabled(normalized, _STAGE_READ_CAPABILITIES)
    elif doctype == "Production Incident":
        can_read = _any_enabled(normalized, _INCIDENT_READ_CAPABILITIES)
    else:
        return {}

    return {
        "read": can_read,
        "select": can_read,
        "create": False,
        "write": False,
        "delete": False,
    }


def supporting_field_permission_projection(
    doctype: str,
    state: Mapping[str, Any] | None,
) -> dict[int, dict[str, bool]]:
    """Keep protected fields on related records aligned with capabilities."""

    normalized = normalize_capability_state(state)
    if doctype != "Cutting Plan":
        return {}
    return {
        1: {
            "read": normalized[Capability.VIEW_COSTS],
            "write": False,
        }
    }


__all__ = [
    "SUPPORTING_DOCTYPES",
    "supporting_field_permission_projection",
    "supporting_standard_permission_projection",
]
