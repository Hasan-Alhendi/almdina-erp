from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


PRINT_FORMAT = "Door Cutting Plan Production A4"


def _archive_filename(order_name: str, revision: int) -> str:
    safe_order = "".join(character if character.isalnum() or character in "-_" else "_" for character in order_name)
    return f"cutting_plan_{safe_order}_rev_{int(revision or 1)}.pdf"


@frappe.whitelist()
def archive_approved_plan_pdf(order_name: str) -> dict[str, Any]:
    require_any_role("Production Manager", "Accounts Management")
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    if not order.approved_plan:
        frappe.throw(_("Order {0} has no Approved Cutting Plan to archive.").format(order.name))

    plan = frappe.get_doc("Cutting Plan", order.approved_plan)
    if plan.status != "Approved" or (plan.plan_kind or "Order") != "Order":
        frappe.throw(_("The linked production Cutting Plan is not an Approved Order Plan."))

    filename = _archive_filename(order.name, plan.revision)
    existing = frappe.db.get_value(
        "File",
        {
            "file_name": filename,
            "attached_to_doctype": "Cutting Plan",
            "attached_to_name": plan.name,
            "is_private": 1,
        },
        ["name", "file_url"],
        as_dict=True,
    )
    if existing:
        return {
            "order": order.name,
            "cutting_plan": plan.name,
            "revision": plan.revision,
            "file": existing.name,
            "file_url": existing.file_url,
            "already_archived": True,
        }

    pdf_content = frappe.get_print(
        "Door Cutting Order",
        order.name,
        print_format=PRINT_FORMAT,
        as_pdf=True,
    )
    if not pdf_content:
        frappe.throw(_("PDF generation returned no content."))

    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": filename,
            "attached_to_doctype": "Cutting Plan",
            "attached_to_name": plan.name,
            "is_private": 1,
            "content": pdf_content,
        }
    ).insert(ignore_permissions=True)

    plan.add_comment(
        "Comment",
        text=_("Official production PDF archived by {0}: {1}").format(
            frappe.session.user,
            filename,
        ),
    )
    return {
        "order": order.name,
        "cutting_plan": plan.name,
        "revision": plan.revision,
        "file": file_doc.name,
        "file_url": file_doc.file_url,
        "already_archived": False,
    }
