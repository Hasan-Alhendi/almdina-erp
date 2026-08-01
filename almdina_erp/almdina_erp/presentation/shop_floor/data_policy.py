from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import Capability


PLAN_AND_DXF_PAYLOAD_FIELDS = frozenset(
    {
        "approved_plan",
        "cutting_plan_html",
        "system_plan_html",
        "custom_plan_html",
        "system_plan_json",
        "custom_plan_json",
        "approved_plan_source",
        "active_plan_source",
        "show_dual_tabs",
        "packing_mode",
        "kerf_mm",
        "trim_margin_mm",
        "cutting_machine_type",
        "can_recalculate_drawing_plan",
        "production_dxf",
        "drawing_dxf_status",
    }
)


def sanitize_shop_floor_detail(
    payload: Mapping[str, Any],
    document_capabilities: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the least-privilege detail payload for the current document.

    Hiding controls in JavaScript is not a data boundary. Cutting layouts,
    optimizer settings, plan snapshots and production DXF URLs are removed on
    the server unless the document grants ``view_cutting_plan``.
    """

    sanitized = dict(payload)
    capabilities = document_capabilities or {}
    if capabilities.get(Capability.VIEW_CUTTING_PLAN) is True:
        return sanitized

    for fieldname in PLAN_AND_DXF_PAYLOAD_FIELDS:
        sanitized.pop(fieldname, None)
    return sanitized


__all__ = [
    "PLAN_AND_DXF_PAYLOAD_FIELDS",
    "sanitize_shop_floor_detail",
]
