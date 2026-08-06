"""Backward-compatible shop-floor API facade.

New code must use the focused command, query, DXF, or infrastructure modules.
This facade preserves historical whitelisted endpoints while delegating every
operation to the canonical capability-protected services. It owns no route,
role, database, or business policy.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable

import frappe


_COMMANDS = "almdina_erp.almdina_erp.services.shop_floor_commands"
_QUERIES = "almdina_erp.almdina_erp.services.shop_floor_query_service"
_DXF = "almdina_erp.almdina_erp.services.shop_floor_dxf_service"
_DISPATCH = "almdina_erp.almdina_erp.services.order_dispatch_service"
_PRODUCTION = "almdina_erp.almdina_erp.services.production_service"


def _delegate(
    module_path: str,
    function_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    function = getattr(import_module(module_path), function_name)
    return function(*args, **kwargs)


def _public_delegate(
    module_path: str,
    function_name: str,
) -> Callable[..., Any]:
    def delegated(*args: Any, **kwargs: Any) -> Any:
        return _delegate(module_path, function_name, *args, **kwargs)

    delegated.__name__ = function_name
    delegated.__qualname__ = function_name
    delegated.__doc__ = f"Compatibility delegate to {module_path}.{function_name}."
    return frappe.whitelist()(delegated)


# Historical API paths remain valid, but every call reaches the canonical
# capability-protected service. No role or route policy is owned here.
get_shop_floor_context = _public_delegate(_QUERIES, "get_shop_floor_context")
get_dispatch_options = _public_delegate(_QUERIES, "get_dispatch_options")
get_revert_targets = _public_delegate(_QUERIES, "get_revert_targets")
get_my_inbox = _public_delegate(_QUERIES, "get_my_inbox")
get_my_archive = _public_delegate(_QUERIES, "get_my_archive")
get_order_shop_floor_detail = _public_delegate(
    _QUERIES,
    "get_order_shop_floor_detail",
)

mark_dxf_exported = _public_delegate(_DXF, "mark_dxf_exported")
upload_production_dxf = _public_delegate(_DXF, "upload_production_dxf")
recalculate_drawing_plan = _public_delegate(_DXF, "recalculate_drawing_plan")
approve_production_dxf = _public_delegate(_DXF, "approve_production_dxf")

get_handoff_workers = _public_delegate(_COMMANDS, "get_handoff_workers")
get_handoff_context = _public_delegate(_COMMANDS, "get_handoff_context")
start_my_stage = _public_delegate(_COMMANDS, "start_my_stage")
handoff_to_next = _public_delegate(_COMMANDS, "handoff_to_next")
mark_delivered = _public_delegate(_COMMANDS, "mark_delivered")
revert_department = _public_delegate(_COMMANDS, "revert_department")
return_order_to_draft = _public_delegate(_COMMANDS, "return_order_to_draft")
dispatch_order = _public_delegate(_DISPATCH, "dispatch_order")


def assert_order_ready_for_dispatch(order: Any) -> None:
    _delegate(_COMMANDS, "assert_order_ready_for_dispatch", order)


def sync_order_status(order_name: str) -> str:
    return _delegate(_PRODUCTION, "sync_order_status", order_name)


__all__ = [
    "approve_production_dxf",
    "assert_order_ready_for_dispatch",
    "dispatch_order",
    "get_dispatch_options",
    "get_handoff_context",
    "get_handoff_workers",
    "get_my_archive",
    "get_my_inbox",
    "get_order_shop_floor_detail",
    "get_revert_targets",
    "get_shop_floor_context",
    "handoff_to_next",
    "mark_delivered",
    "mark_dxf_exported",
    "recalculate_drawing_plan",
    "return_order_to_draft",
    "revert_department",
    "start_my_stage",
    "sync_order_status",
    "upload_production_dxf",
]
