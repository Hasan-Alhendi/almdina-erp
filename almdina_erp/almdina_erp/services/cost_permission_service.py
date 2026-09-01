from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    authoritative_cost_values,
    overlay_authoritative_costs,
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.services.order_edit_policy import assert_order_editable


ORDER_COST_FIELDS = (
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "mdf_cost_usd",
    "cutting_cost_usd",
    "edge_cost_usd",
    "total_cost_usd",
    "special_shapes_baseline_cost_usd",
    "special_shapes_estimated_total_usd",
    "special_shapes_final_total_usd",
    "extra_addons_total_usd",
    "customer_quote_total_usd",
    "customer_quote_status",
    "material_variance_cost_usd",
    "internal_loss_cost_usd",
    "actual_cost_usd",
)
PIECE_COST_FIELDS = (
    "edge_long_rate_usd",
    "edge_width_rate_usd",
    "edge_long_cost_usd",
    "edge_width_cost_usd",
    "edge_cost_usd",
    "edge_rate_usd",
    "special_shape_estimated_unit_price_usd",
    "special_shape_custom_unit_price_usd",
    "special_shape_final_unit_price_usd",
    "special_shape_price_status",
    "special_shape_price_note",
    "special_shape_price_approved_by",
    "special_shape_price_approved_on",
    "clipped_corner_edge_price_usd",
    "clipped_corner_edge_price_status",
    "clipped_corner_edge_price_note",
    "clipped_corner_edge_price_set_by",
    "clipped_corner_edge_price_set_on",
    "extra_double_unit_price_usd",
    "extra_double_total_usd",
    "extra_full_door_double_unit_price_usd",
    "extra_full_door_double_total_usd",
    "extra_liner_unit_price_usd",
    "extra_liner_total_usd",
    "extra_recessed_handle_cutout_unit_price_usd",
    "extra_recessed_handle_cutout_total_usd",
    "extra_addons_total_usd",
)


def _finite_non_negative(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} must be a valid number.").format(label))
    if not math.isfinite(number):
        frappe.throw(_("{0} must be finite.").format(label))
    if number < 0:
        frappe.throw(_("{0} cannot be negative.").format(label))
    return number


def _required_cost_input(value: Any, label: str) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        frappe.throw(
            _("يجب إدخال {0} من صفحة التكلفة.").format(label),
            frappe.ValidationError,
        )
    return _finite_non_negative(value, label)


def _authorized_order(order_name: str, capability: str) -> Any:
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_cutting_plan_capability(order, capability)
    return order


def _locked_order(order_name: str) -> Any:
    """Lock and load one DCO before a focused pricing mutation."""

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    return order


def _require_expected_document_version(order: Any, expected_modified: str | None) -> None:
    """Preserve optimistic concurrency for commands that save the parent DCO.

    Pricing is edited through a focused Cost command instead of the native DCO
    form save. The browser must therefore send the document version it actually
    opened. Advancing that token from an unrelated GET would hide concurrent
    edits, so only a successful mutation may return a new trusted version.
    """

    expected = str(expected_modified or "").strip()
    current = _document_version(order)
    if expected and expected == current:
        return
    frappe.throw(
        _(
            "تم تعديل الطلب بعد فتحه. أعد تحميل الطلب لمراجعة آخر التغييرات "
            "قبل حفظ السعر."
        ),
        frappe.TimestampMismatchError,
    )


def _require_cost_visibility(order: Any) -> None:
    require_cutting_plan_capability(order, Capability.VIEW_COSTS)


def _special_piece(order: Any, piece_name: str) -> Any:
    for piece in order.pieces or []:
        if piece.name == piece_name:
            return piece
    frappe.throw(_("The selected door row does not belong to this order."))


def _piece_snapshot(piece: Any) -> dict[str, Any]:
    return {
        "name": piece.name,
        **{fieldname: getattr(piece, fieldname, None) for fieldname in PIECE_COST_FIELDS},
    }


def _document_version(order: Any) -> str:
    """Return the DCO optimistic-concurrency token after the current command/read."""

    return str(getattr(order, "modified", None) or "")


def _cost_snapshot(order: Any, *, plan: Any | None = None) -> dict[str, Any]:
    order_snapshot = {
        fieldname: getattr(order, fieldname, None)
        for fieldname in ORDER_COST_FIELDS
    }
    if plan is None:
        resolved_order = overlay_authoritative_costs(order, order_snapshot)
    else:
        # Read-after-write must use the exact plan revision that accepted the
        # command. Re-resolving current_working_plan() here can select another
        # Draft/lineage member and repaint stale financial values immediately
        # after a successful save.
        resolved_order = dict(order_snapshot)
        resolved_order.update(authoritative_cost_values(order, plan=plan))
        resolved_order["required_boards"] = int(getattr(plan, "required_boards", 0) or 0)
    return {
        "order_name": order.name,
        "order_modified": _document_version(order),
        "cutting_plan": str(getattr(plan, "name", None) or "") or None,
        "order": resolved_order,
        "pieces": [_piece_snapshot(piece) for piece in (order.pieces or [])],
    }


@frappe.whitelist()
def get_order_cost_snapshot(order_name: str) -> dict[str, Any]:
    """Return cost data only to users granted ``view_costs`` by the administrator."""

    order = _authorized_order(order_name, Capability.VIEW_COSTS)
    return _cost_snapshot(order)


@frappe.whitelist()
def update_order_cost_settings(
    order_name: str,
    board_rate_usd: float | None = None,
    cutting_cost_per_board_usd: float | None = None,
) -> dict[str, Any]:
    """Update plan-owned cost inputs without granting full document write access."""

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = _authorized_order(name, Capability.EDIT_COST_SETTINGS)
    _require_cost_visibility(order)

    board_rate = _required_cost_input(board_rate_usd, _("سعر اللوح"))
    cutting_rate = _required_cost_input(
        cutting_cost_per_board_usd,
        _("أجور القص / لوح"),
    )
    from almdina_erp.almdina_erp.services.cutting_plan_cost_command_service import (
        update_plan_cost_settings,
    )

    saved = update_plan_cost_settings(
        order,
        board_rate_usd=board_rate,
        cutting_cost_per_board_usd=cutting_rate,
    )
    plan_name = str(saved.get("cutting_plan") or "").strip()
    if not plan_name:
        frappe.throw(
            _("تعذر تحديد خطة القص التي حُفظت عليها التكلفة."),
            frappe.ValidationError,
        )
    saved_plan = frappe.get_doc("Cutting Plan", plan_name)
    return _cost_snapshot(order, plan=saved_plan)


@frappe.whitelist()
def approve_special_piece_price(
    order_name: str,
    piece_name: str,
    unit_price_usd: float,
    note: str | None = None,
    expected_modified: str | None = None,
) -> dict[str, Any]:
    """Approve or edit a special-door price through configurable capabilities."""

    order = _locked_order(order_name)
    _require_cost_visibility(order)
    piece = _special_piece(order, piece_name)
    required_capability = (
        Capability.EDIT_SPECIAL_PRICE
        if piece.special_shape_price_status == "Approved"
        else Capability.APPROVE_SPECIAL_PRICE
    )
    require_document_capability(order, required_capability)
    _require_expected_document_version(order, expected_modified)
    assert_order_editable(order)

    if (piece.piece_type or "Regular") != "Special":
        frappe.throw(_("Only a special door can receive a custom inclusive price."))

    price = _finite_non_negative(unit_price_usd, _("Special Unit Price USD"))
    approval_note = str(note or "").strip()
    if len(approval_note) > 500:
        frappe.throw(_("Pricing note cannot exceed 500 characters."))

    piece.special_shape_custom_unit_price_usd = price
    piece.special_shape_price_status = "Approved"
    piece.special_shape_price_note = approval_note
    piece.special_shape_price_approved_by = frappe.session.user
    piece.special_shape_price_approved_on = now_datetime()
    order.flags.special_price_approval_action = True
    order.save(ignore_permissions=True)

    # Ordinary DCO save intentionally does not orchestrate Cutting Plan or
    # commercial pricing. This focused pricing command therefore refreshes the
    # canonical per-piece final price and customer quote projections explicitly
    # after the approved input has been persisted.
    refresh_order_commercial_totals(order)

    return {
        "order_name": order.name,
        "order_modified": _document_version(order),
        "piece_name": piece.name,
        "unit_price_usd": flt(piece.special_shape_final_unit_price_usd),
        "price_status": piece.special_shape_price_status,
        "approved_by": piece.special_shape_price_approved_by,
        "approved_on": piece.special_shape_price_approved_on,
        "required_capability": required_capability,
        "customer_quote_total_usd": flt(order.customer_quote_total_usd),
        "customer_quote_status": order.customer_quote_status,
    }


@frappe.whitelist()
def update_clipped_corner_edge_price(
    order_name: str,
    piece_name: str,
    edge_price_usd: float,
    note: str | None = None,
    expected_modified: str | None = None,
) -> dict[str, Any]:
    """Set or update cut-corner edge banding processing cost via pricing capabilities."""

    order = _locked_order(order_name)
    _require_cost_visibility(order)
    piece = _special_piece(order, piece_name)
    required_capability = (
        Capability.EDIT_SPECIAL_PRICE
        if piece.clipped_corner_edge_price_status == "Priced"
        else Capability.APPROVE_SPECIAL_PRICE
    )
    require_document_capability(order, required_capability)
    _require_expected_document_version(order, expected_modified)
    assert_order_editable(order)

    if (piece.piece_type or "Regular") != "Clipped Corner":
        frappe.throw(_("Only a cut-corner door can receive a custom edge banding price."))

    price = _finite_non_negative(edge_price_usd, _("Cut-Corner Edge Banding Price USD"))
    approval_note = str(note or "").strip()
    if len(approval_note) > 500:
        frappe.throw(_("Pricing note cannot exceed 500 characters."))

    piece.clipped_corner_edge_price_usd = price
    piece.clipped_corner_edge_price_status = "Priced"
    piece.clipped_corner_edge_price_note = approval_note
    piece.clipped_corner_edge_price_set_by = frappe.session.user
    piece.clipped_corner_edge_price_set_on = now_datetime()
    order.flags.special_price_approval_action = True
    order.save(ignore_permissions=True)

    return {
        "order_name": order.name,
        "order_modified": _document_version(order),
        "piece_name": piece.name,
        "edge_price_usd": flt(piece.clipped_corner_edge_price_usd),
        "price_status": piece.clipped_corner_edge_price_status,
        "set_by": piece.clipped_corner_edge_price_set_by,
        "set_on": piece.clipped_corner_edge_price_set_on,
        "required_capability": required_capability,
    }


__all__ = [
    "approve_special_piece_price",
    "get_order_cost_snapshot",
    "update_clipped_corner_edge_price",
    "update_order_cost_settings",
]
