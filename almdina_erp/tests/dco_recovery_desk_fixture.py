from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import enable_setup_wizard_complete

from almdina_erp.almdina_erp.infrastructure.frappe.production_routing_management_repository import (
    list_operational_roles,
)


def _category(doctype: str, name_field: str, parent_field: str, suffix: str) -> str:
    leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
    if leaf:
        return str(leaf)

    root = frappe.db.get_value(doctype, {"is_group": 1}, "name")
    if not root:
        root_doc = frappe.get_doc(
            {
                "doctype": doctype,
                name_field: f"DCO Recovery Fixtures {suffix}",
                "is_group": 1,
            }
        )
        root_doc.insert(ignore_permissions=True)
        root = root_doc.name

    leaf_doc = frappe.get_doc(
        {
            "doctype": doctype,
            name_field: f"DCO Recovery Fixture {suffix}",
            parent_field: root,
            "is_group": 0,
        }
    )
    leaf_doc.insert(ignore_permissions=True)
    return str(leaf_doc.name)


def _customer(suffix: str) -> str:
    group = frappe.db.get_single_value("Selling Settings", "customer_group")
    territory = frappe.db.get_single_value("Selling Settings", "territory")
    if group and frappe.db.get_value("Customer Group", group, "is_group") != 0:
        group = None
    if territory and frappe.db.get_value("Territory", territory, "is_group") != 0:
        territory = None
    group = group or _category(
        "Customer Group", "customer_group_name", "parent_customer_group", suffix
    )
    territory = territory or _category("Territory", "territory_name", "parent_territory", suffix)
    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": f"DCO Recovery Browser {suffix}",
            "customer_type": "Individual",
            "customer_group": group,
            "territory": territory,
        }
    )
    customer.insert(ignore_permissions=True)
    return str(customer.name)


def _edge_type(suffix: str) -> str:
    edge = frappe.get_doc(
        {
            "doctype": "Edge Banding Type",
            "edge_type_name": f"Recovery Browser {suffix}",
            "english_name": "Recovery Browser",
            "width_cm": 2,
            "thickness_mm": 1,
            "rate_usd_per_meter": 1,
        }
    )
    edge.insert(ignore_permissions=True)
    return str(edge.name)


def _route(suffix: str) -> str:
    operational_roles = list_operational_roles()
    if not operational_roles:
        frappe.throw("No eligible operational role is available for the Desk fixture.")
    code = f"DeskRecovery{suffix}"
    stage = frappe.get_doc(
        {
            "doctype": "Production Stage Definition",
            "stage_code": code,
            "stage_label": f"مرحلة اختبار الاسترداد {suffix}",
        }
    )
    stage.insert(ignore_permissions=True)
    route = frappe.get_doc(
        {
            "doctype": "Production Routing",
            "routing_name": f"DCO Recovery Browser {suffix}",
            "disabled": 0,
            "stages": [
                {
                    "sequence": 1,
                    "stage_definition": stage.name,
                    "operational_role": operational_roles[0],
                    "required": 1,
                    "is_planning_stage": 1,
                }
            ],
        }
    )
    route.insert(ignore_permissions=True)
    return str(route.name)


def _order(suffix: str, customer: str, edge_type: str, route: str) -> str:
    order = frappe.get_doc(
        {
            "doctype": "Door Cutting Order",
            "customer": customer,
            "board_description": "Recovery browser fixture MDF",
            "board_length_cm": 244,
            "board_width_cm": 122,
            "default_edge_type": edge_type,
            "edge_color": "White",
            "production_path": route,
            "order_notes": f"Official baseline {suffix}",
            "pieces": [
                {
                    "piece_type": "Regular",
                    "width_cm": 60,
                    "length_cm": 100,
                    "qty": 1,
                }
            ],
        }
    )
    order.insert(ignore_permissions=True)
    return str(order.name)


def create_desk_edit_recovery_fixtures() -> dict[str, str]:
    """Create isolated real Frappe records used only by Desk browser CI."""

    frappe.set_user("Administrator")
    enable_setup_wizard_complete("frappe")
    enable_setup_wizard_complete("erpnext")
    suffix = uuid4().hex[:10]
    customer = _customer(suffix)
    edge_type = _edge_type(suffix)
    route = _route(suffix)
    fixtures = {
        "restore": _order(f"restore-{suffix}", customer, edge_type, route),
        "dispatch": _order(f"dispatch-{suffix}", customer, edge_type, route),
        "route": route,
    }
    destination = os.environ.get("DCO_DESK_FIXTURE_FILE")
    if not destination:
        frappe.throw("DCO_DESK_FIXTURE_FILE must point to an isolated CI temp file.")
    Path(destination).write_text(json.dumps(fixtures), encoding="utf-8")
    return fixtures
