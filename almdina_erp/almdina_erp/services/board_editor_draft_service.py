"""Write path for one board-editor draft.

VIEW is not enough. The Cutting Plan row, its snapshot, approval, and CUT_PATH
are not modified.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_save import (
    draft_write_allowed,
    execute_begin_from_current_source,
    execute_save,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    catalog_from_projection,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import LOCKED_ORDER_STATUSES
from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_draft_store import (
    FrappeBoardEditorDraftStore,
    _archive_column_ready,
)
from almdina_erp.almdina_erp.services.board_editor_query_service import (
    _authorized_order,
    _capabilities,
    _load_plan_for_order,
    _plan_view_allowed,
    _require_use_board_editor,
    _use_board_editor_allowed,
    get_board_editor_projection,
)


def _authorize_draft_write(order_name: str, plan_name: str):
    order = _authorized_order(order_name)
    _require_use_board_editor(order)
    plan = _load_plan_for_order(order, plan_name)
    order_status = str(getattr(order, "status", "") or "")
    if order_status in LOCKED_ORDER_STATUSES:
        return order, plan, order_status, {"ok": False, "code": "order_locked"}
    capabilities = _capabilities(order)
    allowed = draft_write_allowed(
        has_edit_capability=_use_board_editor_allowed(order),
        has_plan_view=_plan_view_allowed(order, plan, capabilities),
        order_status=order_status,
    )
    if not allowed:
        frappe.throw(
            _("You do not have permission to save this board editor layout."),
            frappe.PermissionError,
        )
    return order, plan, order_status, None


@frappe.whitelist(methods=["POST"])
def save_board_editor_draft(
    order_name: str,
    plan_name: str,
    expected_draft_version: int = 0,
    source_content_revision: str = "",
    layout: Any = None,
) -> dict[str, Any]:
    """Save edit fields for one order and source plan."""

    order, plan, order_status, early = _authorize_draft_write(order_name, plan_name)
    if early is not None:
        return early

    payload = get_board_editor_projection(order_name, plan_name)
    if str((payload.get("plan") or {}).get("name") or "") != str(plan.name):
        frappe.throw(
            _("The selected cutting plan does not belong to this order."),
            frappe.PermissionError,
        )
    parsed = _parse_layout(layout)
    result = execute_save(
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "expected_draft_version": expected_draft_version,
            "source_content_revision": str(source_content_revision or ""),
            "layout": parsed,
        },
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "order_status": order_status,
            "source_input_fingerprint": str((payload.get("plan") or {}).get("input_fingerprint") or ""),
            "source_content_revision": str(
                (payload.get("plan") or {}).get("content_revision_token") or ""
            ),
            "catalog": catalog_from_projection(payload.get("projection") or {}),
        },
        FrappeBoardEditorDraftStore(),
    )
    result.pop("layout", None)
    return result


@frappe.whitelist(methods=["POST"])
def begin_board_editor_draft_from_current_source(
    order_name: str,
    plan_name: str,
    expected_draft_version: int = 0,
    source_content_revision: str = "",
) -> dict[str, Any]:
    """Archive an incompatible draft and start a fresh layout on the live source.

    Does not mutate Approved Cutting Plan rows. Prior poses are archived, not
    applied onto the new source identity layout.
    """

    if not _archive_column_ready():
        frappe.throw(
            _("Board editor draft archive storage is not installed. Run migrate."),
            frappe.ValidationError,
        )

    order, plan, order_status, early = _authorize_draft_write(order_name, plan_name)
    if early is not None:
        return early

    payload = get_board_editor_projection(order_name, plan_name)
    if str((payload.get("plan") or {}).get("name") or "") != str(plan.name):
        frappe.throw(
            _("The selected cutting plan does not belong to this order."),
            frappe.PermissionError,
        )
    result = execute_begin_from_current_source(
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "expected_draft_version": expected_draft_version,
            "source_content_revision": str(source_content_revision or ""),
        },
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "order_status": order_status,
            "source_input_fingerprint": str((payload.get("plan") or {}).get("input_fingerprint") or ""),
            "source_content_revision": str(
                (payload.get("plan") or {}).get("content_revision_token") or ""
            ),
            "catalog": catalog_from_projection(payload.get("projection") or {}),
            "projection": payload.get("projection") or {},
        },
        FrappeBoardEditorDraftStore(),
    )
    result.pop("layout", None)
    return result


def _parse_layout(layout: Any) -> Any:
    if isinstance(layout, str):
        try:
            return json.loads(layout)
        except ValueError:
            return None
    return layout


__all__ = [
    "save_board_editor_draft",
    "begin_board_editor_draft_from_current_source",
]
