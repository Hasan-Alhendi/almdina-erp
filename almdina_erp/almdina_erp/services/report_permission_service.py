from __future__ import annotations

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.security.report_access import (
    ReportAccess,
    build_report_access,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)


def current_report_access() -> ReportAccess:
    return build_report_access(granted_capabilities())


def require_operational_report_access() -> ReportAccess:
    access = current_report_access()
    granted = granted_capabilities()
    if access.operational and Capability.VIEW_ORDERS in granted:
        return access
    frappe.throw(
        _("لا تملك صلاحية عرض تقارير المعمل التشغيلية. يجب أن يملك دورك صلاحية عرض التقارير التشغيلية وصلاحية عرض الطلبات."),
        frappe.PermissionError,
    )
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def get_report_access_context() -> dict[str, bool]:
    access = require_operational_report_access()
    return {
        "operational": access.operational,
        "financial": access.financial,
    }


__all__ = [
    "current_report_access",
    "get_report_access_context",
    "require_operational_report_access",
]
