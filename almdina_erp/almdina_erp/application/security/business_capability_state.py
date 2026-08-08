from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


_EDGE_ADMIN_ACTIONS = frozenset(
    {
        Capability.CREATE_EDGE_BANDING_TYPES,
        Capability.EDIT_EDGE_BANDING_TYPES,
        Capability.DELETE_EDGE_BANDING_TYPES,
    }
)


def normalize_business_capability_state(
    raw: Mapping[str, Any] | None,
) -> dict[str, bool]:
    """Normalize business authority without promoting lookup dependencies.

    Order entry needs Customer and Edge Banding Type records as lookup data, but
    that technical dependency must not become a business grant that exposes the
    corresponding administration surfaces. Frappe projections may still grant
    read/select separately for lookup UX.

    Edge-band CRUD actions remain a genuine business dependency of edge-band
    viewing, so any explicit create/edit/delete grant also enables its view grant.
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
    return normalized


__all__ = ["normalize_business_capability_state"]
