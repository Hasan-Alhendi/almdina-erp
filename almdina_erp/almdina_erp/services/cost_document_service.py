from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
    build_internal_cost_report_document,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
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
    "customer_quote_total_usd",
    "customer_quote_status",
    "material_variance_cost_usd",
    "internal_loss_cost_usd",
    "actual_cost_usd",
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
    "special_shape_estimated_unit_price_usd",
    "special_shape_custom_unit_price_usd",
    "special_shape_final_unit_price_usd",
    "special_shape_price_status",
    "special_shape_price_note",
    "special_shape_price_approved_by",
    "special_shape_price_approved_on",
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
    return (
        _snapshot(order, ORDER_DOCUMENT_FIELDS),
        [
            _snapshot(piece, PIECE_DOCUMENT_FIELDS)
            for piece in (order.pieces or [])
        ],
    )


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


@frappe.whitelist()
def get_customer_invoice_document(order_name: str) -> dict[str, Any]:
    """Return a customer invoice after read and explicit print authorization."""

    order = _authorized_order(
        order_name,
        Capability.PRINT_CUSTOMER_INVOICE,
        requires_cost_access=False,
    )
    order_snapshot, pieces = _document_context(order)
    return _finalize(
        build_customer_invoice_document(order_snapshot, pieces),
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
