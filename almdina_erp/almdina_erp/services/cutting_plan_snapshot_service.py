"""Retired pre-A6 Cutting Plan snapshot persistence surface.

The original implementation treated ``Door Cutting Order`` as the owner of
optimizer settings, plan JSON, DXF state, cost values, and production locking.
A6.1/A6.2 moved those responsibilities to canonical ``Cutting Plan`` commands
and stopped the compatibility writers back to DCO.

This module intentionally remains as a fail-closed import target during the
migration window so an unknown historical Python caller cannot silently revive
the old aggregate model. HTTP compatibility paths are already routed by hooks or
``cutting_plan_service`` to the focused canonical services.
"""

from __future__ import annotations

from typing import Any, NoReturn

import frappe
from frappe import _


_RETIRED_SNAPSHOT_MESSAGE = _(
    "The legacy Door Cutting Order snapshot API has been retired. "
    "Use the canonical Cutting Plan command services."
)


def _retired_snapshot_api() -> NoReturn:
    frappe.throw(_RETIRED_SNAPSHOT_MESSAGE, frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


def create_plan_from_order(
    order: Any,
    snapshot_override: dict[str, Any] | None = None,
    *,
    plan_kind: str = "Order",
) -> NoReturn:
    """Reject the former DCO-to-Cutting-Plan snapshot constructor."""

    del order, snapshot_override, plan_kind
    _retired_snapshot_api()


def approve_plan(plan: Any) -> NoReturn:
    """Reject the former direct Plan approval bypass."""

    del plan
    _retired_snapshot_api()


def lock_order_for_production(
    order: Any,
    *,
    preserve_status: bool = False,
    plan_source: str = "System",
) -> NoReturn:
    """Reject the former order-owned plan lock/persistence path."""

    del order, preserve_status, plan_source
    _retired_snapshot_api()


__all__ = [
    "approve_plan",
    "create_plan_from_order",
    "lock_order_for_production",
]
