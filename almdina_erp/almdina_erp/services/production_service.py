"""Backward-compatible production-service facade.

Historical Python helpers remain available as delegates while active shop-floor
code uses focused command, status-sync, and infrastructure modules. Historical
HTTP stage-control methods remain fail-closed or route to the protected legacy
adapter through hooks.
"""

from __future__ import annotations

from typing import Any

import frappe


def ensure_default_stages(
    order_name: str,
    approved_by: str | None = None,
) -> list[str]:
    """Compatibility delegate to the focused stage-bootstrap owner."""

    from almdina_erp.almdina_erp.services.production_stage_bootstrap_service import (
        ensure_default_stages as ensure,
    )

    return ensure(order_name, approved_by)


def sync_order_status(order_name: str) -> str:
    """Compatibility delegate to the focused order-status owner."""

    from almdina_erp.almdina_erp.services.order_status_sync_service import (
        sync_order_status as sync,
    )

    return sync(order_name)


@frappe.whitelist()
def start_stage(
    stage_name: str,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        start_legacy_stage,
    )

    return start_legacy_stage(stage_name, assigned_to)


@frappe.whitelist()
def finish_stage(
    stage_name: str,
    completed_qty: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        finish_legacy_stage,
    )

    return finish_legacy_stage(stage_name, completed_qty, notes)


@frappe.whitelist()
def pause_stage(stage_name: str, reason: str | None = None) -> dict[str, Any]:
    del stage_name, reason
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        retired_product_endpoint,
    )

    return retired_product_endpoint()


@frappe.whitelist()
def resume_stage(stage_name: str) -> dict[str, Any]:
    del stage_name
    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        retired_product_endpoint,
    )

    return retired_product_endpoint()


__all__ = [
    "ensure_default_stages",
    "finish_stage",
    "pause_stage",
    "resume_stage",
    "start_stage",
    "sync_order_status",
]
