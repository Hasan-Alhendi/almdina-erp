from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.application.costing.customer_invoice_addon_summary import (
    summarize_extra_addon_lines,
)
from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
    build_internal_cost_report_document,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    pending_custom_edge_price_labels,
)
from almdina_erp.almdina_erp.domain.cutting.physical_execution_contract import physical_execution_for_snapshot
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    overlay_authoritative_costs,
)


ORDER_DOCUMENT_FIELDS = (
    "name",
    "customer",
    "order_date",
    "board_description",
    "default_edge_type",
    "edge_color",
    "order_notes",
    "status",
    "revision",
    "approved_plan",
    "required_boards",
    "total_area_m2",
    "total_edge_meters",
    "waste_area_m2",
    "waste_percent",
    "packing_method",
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
    "offcut_price_usd",
)
PIECE_DOCUMENT_FIELDS = (
    "name",
    "piece_no",
    "piece_type",
    "width_cm",
    "length_cm",
    "qty",
    "edge_type",
    "edge_meters",
    "edge_rate_usd",
    "edge_cost_usd",
    "notes",
    "special_shape_drawing_json",
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
    "extra_double",
    "extra_double_unit_price_usd",
    "extra_double_total_usd",
    "extra_full_door_double",
    "extra_full_door_double_unit_price_usd",
    "extra_full_door_double_total_usd",
    "extra_liner",
    "extra_liner_unit_price_usd",
    "extra_liner_total_usd",
    "extra_back_groove",
    "extra_back_groove_unit_price_usd",
    "extra_back_groove_total_usd",
    "extra_recessed_handle_cutout",
    "extra_recessed_handle_cutout_unit_price_usd",
    "extra_recessed_handle_cutout_total_usd",
    "extra_addons_total_usd",
)
_FACTORY_SCALED_TOTAL_FIELDS = (
    "extra_double_total_usd",
    "extra_full_door_double_total_usd",
    "extra_liner_total_usd",
    "extra_back_groove_total_usd",
    "extra_recessed_handle_cutout_total_usd",
    "extra_addons_total_usd",
)


def _snapshot(source: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {fieldname: getattr(source, fieldname, None) for fieldname in fields}


def _authorized_order(
    order_name: str,
    print_capability: str,
    *,
    requires_cost_access: bool,
) -> Any:
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    if requires_cost_access:
        require_document_capability(order, Capability.VIEW_COSTS)
    require_document_capability(order, print_capability)
    return order


def _document_context(order: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    order_snapshot = overlay_authoritative_costs(
        order,
        _snapshot(order, ORDER_DOCUMENT_FIELDS),
    )
    plan = None
    if order.approved_plan:
        plan = frappe.get_doc("Cutting Plan", order.approved_plan)
    execution_qty_by_source: dict[int, int] = {}
    physical_qty_by_source: dict[int, int] = {}
    if plan:
        snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
        execution = physical_execution_for_snapshot(snapshot)
        if execution is not None:
            execution_qty_by_source = dict(execution.factory_processing_qty_by_source_piece_no)
            physical_qty_by_source = dict(execution.physical_qty_by_source_piece_no)
        order_snapshot["offcut_price_usd"] = getattr(plan, "offcut_price_usd", 0)
        order_snapshot["offcut_factory_factory"] = bool(
            execution and execution.has_factory_source_offcut
        )
    return (
        order_snapshot,
        _commercial_piece_snapshots(
            order.pieces or [],
            execution_qty_by_source,
            physical_qty_by_source,
        ),
    )


def _commercial_piece_snapshots(
    pieces: list[Any],
    execution_qty_by_source: dict[int, int],
    physical_qty_by_source: dict[int, int],
) -> list[dict[str, Any]]:
    """Annotate customer rows with plan-derived factory service quantities."""

    snapshots: list[dict[str, Any]] = []
    for source_piece_no, piece in enumerate(pieces, start=1):
        row = _snapshot(piece, PIECE_DOCUMENT_FIELDS)
        physical_qty = physical_qty_by_source.get(source_piece_no)
        if physical_qty is None:
            snapshots.append(row)
            continue
        factory_qty = execution_qty_by_source.get(source_piece_no, 0)
        row["factory_execution_qty"] = factory_qty
        ratio = factory_qty / physical_qty if physical_qty else 0
        for fieldname in ("edge_meters", "edge_cost_usd", *_FACTORY_SCALED_TOTAL_FIELDS):
            row[fieldname] = (row.get(fieldname) or 0) * ratio
        snapshots.append(row)
    return snapshots


def _finalize(payload: dict[str, Any], order: Any) -> dict[str, Any]:
    return {
        **payload,
        "order_name": order.name,
        "generated_by": frappe.session.user,
        "generated_on": now_datetime(),
        "source_status": order.status,
        "source_revision": order.revision,
        "source_approved_plan": order.approved_plan,
    }


def _require_custom_edge_prices(pieces: list[dict[str, Any]]) -> None:
    pending = pending_custom_edge_price_labels(pieces)
    if pending:
        frappe.throw(
            _(
                "أدخل السعر الخاص الشامل للدرف الخاصة وسعر قشاط درف "
                "الزاوية المقصوصة قبل طباعة الفاتورة. المتبقي: {0}."
            ).format("، ".join(pending))
        )


def _summarize_customer_invoice(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply customer-only line summarization without changing stored costing data."""

    return {
        **payload,
        "lines": summarize_extra_addon_lines(payload.get("lines") or []),
    }


@frappe.whitelist()
def get_customer_invoice_document(order_name: str) -> dict[str, Any]:
    """Return a customer invoice after read and explicit print authorization."""

    order = _authorized_order(
        order_name,
        Capability.PRINT_CUSTOMER_INVOICE,
        requires_cost_access=False,
    )
    order_snapshot, pieces = _document_context(order)
    # Pricing readiness follows the same physical execution projection used by
    # the invoice builder. Customer-executed OFFCUT copies are real requirements
    # but they must never block a factory-service invoice price.
    _require_custom_edge_prices(pieces)
    return _finalize(
        _summarize_customer_invoice(
            build_customer_invoice_document(order_snapshot, pieces)
        ),
        order,
    )


@frappe.whitelist()
def get_internal_cost_report_document(order_name: str) -> dict[str, Any]:
    """Return the confidential internal report to explicitly authorized users."""

    order = _authorized_order(
        order_name,
        Capability.PRINT_INTERNAL_COST_REPORT,
        requires_cost_access=True,
    )
    order_snapshot, pieces = _document_context(order)
    return _finalize(
        build_internal_cost_report_document(order_snapshot, pieces),
        order,
    )


__all__ = [
    "get_customer_invoice_document",
    "get_internal_cost_report_document",
]
