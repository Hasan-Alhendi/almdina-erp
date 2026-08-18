from __future__ import annotations

from typing import Any

from almdina_erp.almdina_erp.application.cutting.plan_revisions import PlanSettings
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    factory_default_plan_settings,
    seed_plan_settings,
)


def preview_plan_settings(order_name: str | None = None) -> PlanSettings:
    """Resolve preview settings from Cutting Plan lineage, never DCO columns."""

    name = str(order_name or "").strip()
    if name and not name.startswith("new-"):
        return seed_plan_settings(name)
    return factory_default_plan_settings()


def apply_preview_plan_settings(
    document: Any,
    *,
    order_name: str | None = None,
    settings: PlanSettings | None = None,
) -> PlanSettings:
    """Attach plan-owned settings to an in-memory preview document only.

    The legacy preview optimizer still consumes a DCO-shaped object. A6.4 keeps
    that computation isolated without requiring persisted DCO plan fields: these
    attributes are assigned after document construction and are never saved.
    """

    resolved = settings or preview_plan_settings(order_name)
    document.packing_mode = resolved.optimization_mode
    document.cutting_machine_type = resolved.machine_type
    document.optimization_time_limit_sec = resolved.optimization_time_limit_sec
    document.kerf_mm = resolved.kerf_mm
    document.trim_margin_mm = resolved.trim_margin_mm
    return resolved


def clear_transient_plan_results(document: Any) -> None:
    """Initialize volatile preview outputs independently from DocType metadata."""

    document.flags._transient_plan_preview = True
    for fieldname, value in (
        ("cutting_plan_json", ""),
        ("system_plan_json", ""),
        ("custom_plan_json", ""),
        ("calculated_plan_input_hash", ""),
        ("calculated_plan_metadata_hash", ""),
        ("plan_needs_recalculation", 1),
        ("required_boards", 0),
        ("waste_area_m2", 0.0),
        ("waste_percent", 0.0),
        ("packing_method", ""),
        ("packing_score", ""),
        ("engine_version", ""),
    ):
        setattr(document, fieldname, value)


__all__ = [
    "apply_preview_plan_settings",
    "clear_transient_plan_results",
    "preview_plan_settings",
]
