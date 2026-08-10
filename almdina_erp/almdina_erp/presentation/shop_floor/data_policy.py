from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.security.authorization import Capability


PLAN_PAYLOAD_FIELDS = frozenset(
    {
        "approved_plan",
        "cutting_plan_html",
        "system_plan_html",
        "custom_plan_html",
        "approved_plan_html",
        "system_plan_json",
        "custom_plan_json",
        "approved_plan_source",
        "active_plan_source",
        "visible_plan_tabs",
        "show_dual_tabs",
        "packing_mode",
        "kerf_mm",
        "trim_margin_mm",
        "cutting_machine_type",
        "can_recalculate_drawing_plan",
    }
)

DXF_PAYLOAD_FIELDS = frozenset(
    {
        "production_dxf",
        "drawing_dxf_status",
    }
)

DXF_VISIBILITY_CAPABILITIES = frozenset(
    {
        Capability.VIEW_DRAWING_WORKSPACE,
        Capability.EXPORT_DXF,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.APPROVE_DXF,
    }
)

# Compatibility export for callers/tests that referenced the earlier combined set.
PLAN_AND_DXF_PAYLOAD_FIELDS = PLAN_PAYLOAD_FIELDS | DXF_PAYLOAD_FIELDS


def _has_capability(
    capabilities: Mapping[str, Any] | Iterable[str] | None,
    capability: str,
) -> bool:
    if capabilities is None:
        return False
    if isinstance(capabilities, Mapping):
        return capabilities.get(capability) is True
    return capability in capabilities


def _has_any_capability(
    capabilities: Mapping[str, Any] | Iterable[str] | None,
    requested: Iterable[str],
) -> bool:
    return any(_has_capability(capabilities, capability) for capability in requested)


def _remove_fields(payload: dict[str, Any], fields: Iterable[str]) -> None:
    for fieldname in fields:
        payload.pop(fieldname, None)


def sanitize_shop_floor_summary(
    rows: Sequence[Mapping[str, Any]],
    capabilities: Mapping[str, Any] | Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Remove protected plan and DXF data from inbox/archive summaries."""

    can_view_plan = _has_capability(capabilities, Capability.VIEW_CUTTING_PLAN)
    can_view_dxf = _has_any_capability(capabilities, DXF_VISIBILITY_CAPABILITIES)
    sanitized_rows: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        if not can_view_plan:
            row.pop("approved_plan", None)
        if not can_view_dxf:
            _remove_fields(row, DXF_PAYLOAD_FIELDS)
        sanitized_rows.append(row)
    return sanitized_rows


def sanitize_shop_floor_detail(
    payload: Mapping[str, Any],
    document_capabilities: Mapping[str, Any] | Iterable[str] | None,
) -> dict[str, Any]:
    """Return a least-privilege detail payload for the current document.

    Cutting layouts and optimizer settings require ``view_cutting_plan``.
    Production DXF URLs and status require an explicit drawing/DXF capability.
    Hiding controls in JavaScript is never treated as a data boundary.
    """

    sanitized = dict(payload)
    if not _has_capability(
        document_capabilities,
        Capability.VIEW_CUTTING_PLAN,
    ):
        _remove_fields(sanitized, PLAN_PAYLOAD_FIELDS)

    if not _has_any_capability(
        document_capabilities,
        DXF_VISIBILITY_CAPABILITIES,
    ):
        _remove_fields(sanitized, DXF_PAYLOAD_FIELDS)

    return sanitized


__all__ = [
    "DXF_PAYLOAD_FIELDS",
    "DXF_VISIBILITY_CAPABILITIES",
    "PLAN_AND_DXF_PAYLOAD_FIELDS",
    "PLAN_PAYLOAD_FIELDS",
    "sanitize_shop_floor_detail",
    "sanitize_shop_floor_summary",
]
