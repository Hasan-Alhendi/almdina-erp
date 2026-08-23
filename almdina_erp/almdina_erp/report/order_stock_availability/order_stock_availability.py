from __future__ import annotations

from typing import Any

from frappe import _

from almdina_erp.almdina_erp.services.report_permission_service import (
    require_operational_report_access,
)


def execute(filters: dict[str, Any] | None = None):
    """Keep the historical report surface fail-closed after stock retirement."""

    del filters
    require_operational_report_access()

    from almdina_erp.almdina_erp.services.legacy_endpoint_service import (
        retired_product_endpoint,
    )

    return retired_product_endpoint()


def get_columns():
    return [
        {"label": _("Order"), "fieldname": "order_name", "fieldtype": "Link", "options": "Door Cutting Order", "width": 150},
        {"label": _("Date"), "fieldname": "order_date", "fieldtype": "Date", "width": 95},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
        {"label": _("Order Status"), "fieldname": "order_status", "fieldtype": "Data", "width": 135},
        {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 145},
        {"label": _("Material Kind"), "fieldname": "kind", "fieldtype": "Data", "width": 105},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 145},
        {"label": _("Required Stock Qty"), "fieldname": "required_qty", "fieldtype": "Float", "width": 115},
        {"label": _("Physical Stock"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 105},
        {"label": _("Reserved Elsewhere"), "fieldname": "reserved_qty", "fieldtype": "Float", "width": 115},
        {"label": _("Available After Reservations"), "fieldname": "available_qty", "fieldtype": "Float", "width": 145},
        {"label": _("Shortage"), "fieldname": "shortage_qty", "fieldtype": "Float", "width": 90},
        {"label": _("Business Unit"), "fieldname": "planned_unit", "fieldtype": "Data", "width": 95},
        {"label": _("Planned Business Qty"), "fieldname": "planned_qty", "fieldtype": "Float", "width": 125},
    ]
