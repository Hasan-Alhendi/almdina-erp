"""Retired dual-plan field facade kept only for historical read compatibility.

Canonical runtime reads come from ``Cutting Plan``. The remaining export bridge
may call the read helpers below for pre-canonical records until data migration.
Legacy setters deliberately fail closed so this module can never revive DCO plan
projections.
"""

from __future__ import annotations

from typing import Any, NoReturn

from almdina_erp.almdina_erp.infrastructure.frappe.legacy_plan_projection_reader import (
    legacy_approved_plan_source,
    legacy_custom_plan_json,
    legacy_system_plan_json,
)


def get_system_plan_json(order: Any) -> str:
    return legacy_system_plan_json(order)


def get_custom_plan_json(order: Any) -> str:
    return legacy_custom_plan_json(order)


def get_approved_plan_source(order: Any, default: str = "System") -> str:
    return legacy_approved_plan_source(order, default)


def _retired_writer() -> NoReturn:
    raise RuntimeError(
        "Door Cutting Order plan projections are read-only migration data; "
        "persist canonical state through Cutting Plan commands."
    )


def set_system_plan_json_if_available(order: Any, payload: str) -> NoReturn:
    del order, payload
    _retired_writer()


def set_custom_plan_json_if_available(order: Any, payload: str) -> NoReturn:
    del order, payload
    _retired_writer()


__all__ = [
    "get_approved_plan_source",
    "get_custom_plan_json",
    "get_system_plan_json",
    "set_custom_plan_json_if_available",
    "set_system_plan_json_if_available",
]
