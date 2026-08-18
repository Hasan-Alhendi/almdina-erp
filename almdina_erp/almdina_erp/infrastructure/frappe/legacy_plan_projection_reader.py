"""Read-only migration boundary for pre-canonical DCO plan projections.

A6.1/A6.2 made ``Cutting Plan`` authoritative and stopped all active writers to
legacy Door Cutting Order plan fields. A small number of historical records may
still predate canonical Cutting Plan revisions, so compatibility reads live in
this single boundary until the data migration/schema-retirement phase.

No production decision may depend on these helpers. They must never mutate a
Door Cutting Order, create a Cutting Plan, or bypass permissions.
"""

from __future__ import annotations

from typing import Any

from frappe.utils import flt


def legacy_selected_plan_json(order: Any) -> str:
    return str(getattr(order, "cutting_plan_json", None) or "")


def legacy_system_plan_json(order: Any) -> str:
    return str(
        getattr(order, "system_plan_json", None)
        or getattr(order, "cutting_plan_json", None)
        or ""
    )


def legacy_custom_plan_json(order: Any) -> str:
    return str(getattr(order, "custom_plan_json", None) or "")


def legacy_production_dxf(order: Any) -> str:
    return str(getattr(order, "production_dxf", None) or "")


def legacy_kerf_mm(order: Any) -> float:
    return flt(getattr(order, "kerf_mm", 0))


__all__ = [
    "legacy_custom_plan_json",
    "legacy_kerf_mm",
    "legacy_production_dxf",
    "legacy_selected_plan_json",
    "legacy_system_plan_json",
]
