from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    require_document_capability,
    require_doctype_capability,
)


_OPERATIONAL_FIELDS = (
    "name",
    "edge_type_name",
    "width_cm",
    "thickness_mm",
    "edge_color",
    "finish_type",
    "application_method",
)
_FINANCIAL_FIELD = "rate_usd_per_meter"


def _authorize_lookup(order_name: str) -> None:
    normalized_name = str(order_name or "").strip()
    if not normalized_name or normalized_name.startswith("new-"):
        require_doctype_capability(
            Capability.CREATE_ORDER,
            message=_("لا تملك صلاحية إنشاء طلب واختيار نوع القشاط له."),
        )
        return

    order = frappe.get_doc("Door Cutting Order", normalized_name)
    order.check_permission("read")
    require_document_capability(
        order,
        Capability.VIEW_ORDERS,
        message=_("لا تملك صلاحية عرض هذا الطلب أو أنواع القشاط التشغيلية الخاصة به."),
    )


def _serialize_row(row: Any, *, include_financial: bool) -> dict[str, Any]:
    payload = {
        "name": str(row.name or ""),
        "edge_type_name": str(row.edge_type_name or row.name or ""),
        "width_cm": row.width_cm,
        "thickness_mm": row.thickness_mm,
        "edge_color": str(row.edge_color or ""),
        "finish_type": str(row.finish_type or ""),
        "application_method": str(row.application_method or ""),
    }
    if include_financial:
        payload[_FINANCIAL_FIELD] = row.rate_usd_per_meter
    return payload


@frappe.whitelist()
def get_order_edge_banding_options(order_name: str = "") -> dict[str, Any]:
    """Return order-safe edge-band lookup data without granting master-data access.

    ``Edge Banding Type`` is factory master data and may contain protected pricing.
    Order viewers still need the operational profile list to understand which sides
    are banded and to use the order's profile dropdowns.  This endpoint is the
    explicit bridge: it authorizes against the order, reads the master data on the
    server, and strips financial fields unless ``view_costs`` is granted.
    """

    _authorize_lookup(order_name)
    include_financial = doctype_has_capability(Capability.VIEW_COSTS)
    fields = list(_OPERATIONAL_FIELDS)
    if include_financial:
        fields.append(_FINANCIAL_FIELD)

    rows = frappe.get_all(
        "Edge Banding Type",
        filters={"disabled": 0},
        fields=fields,
        order_by="width_cm asc, edge_type_name asc",
        limit_page_length=200,
    )
    return {
        "options": [
            _serialize_row(row, include_financial=include_financial)
            for row in rows
        ],
        "include_financial": include_financial,
    }


__all__ = ["get_order_edge_banding_options"]
