"""Disposable fixtures for the isolated Phase 1B Frappe Desk job only."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import erpnext
import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_membership import MEMBERSHIP_FIELD


EXPECTED = {"frappe": "16.17.5", "erpnext": "16.17.0"}


def _versions() -> dict[str, str]:
    versions = {"frappe": frappe.__version__, "erpnext": erpnext.__version__}
    if versions != EXPECTED:
        raise RuntimeError(f"Pinned P0 runtime required: {EXPECTED}; found {versions}")
    return versions


def _leaf(doctype: str, name_field: str, parent_field: str, suffix: str) -> str:
    name = frappe.db.get_value(doctype, {"is_group": 0}, "name")
    if name:
        return str(name)
    root = frappe.db.get_value(doctype, {"is_group": 1}, "name")
    if not root:
        root = frappe.get_doc(
            {"doctype": doctype, name_field: f"P0 root {suffix}", "is_group": 1}
        ).insert(ignore_permissions=True).name
    return str(
        frappe.get_doc(
            {
                "doctype": doctype,
                name_field: f"P0 leaf {suffix}",
                parent_field: root,
                "is_group": 0,
            }
        ).insert(ignore_permissions=True).name
    )


def prepare() -> dict[str, object]:
    frappe.set_user("Administrator")
    versions = _versions()
    if not frappe.is_setup_complete():
        suffix = uuid4().hex[:8]
        setup_complete(
            {
                "language": "English", "lang": "en", "country": "United States",
                "currency": "USD", "timezone": "UTC",
                "company_name": f"P0 Isolated {suffix}",
                "company_abbr": f"P{suffix[:6]}",
                "chart_of_accounts": "Standard", "fy_start_date": "2026-01-01",
                "fy_end_date": "2026-12-31", "domain": "Manufacturing",
                "setup_demo": 0,
            }
        )
        frappe.db.commit()
        frappe.clear_cache()
    if not frappe.is_setup_complete():
        raise RuntimeError("Frappe Setup Wizard did not complete")

    suffix = uuid4().hex[:10]
    group = frappe.db.get_single_value("Selling Settings", "customer_group")
    if group and frappe.db.get_value("Customer Group", group, "is_group") != 0:
        group = None
    territory = frappe.db.get_single_value("Selling Settings", "territory")
    if territory and frappe.db.get_value("Territory", territory, "is_group") != 0:
        territory = None
    customer = frappe.get_doc(
        {
            "doctype": "Customer", "customer_name": f"P0 Isolated {suffix}",
            "customer_type": "Individual",
            "customer_group": group or _leaf("Customer Group", "customer_group_name", "parent_customer_group", suffix),
            "territory": territory or _leaf("Territory", "territory_name", "parent_territory", suffix),
        }
    ).insert(ignore_permissions=True)
    edge = frappe.get_doc(
        {
            "doctype": "Edge Banding Type", "edge_type_name": f"P0 {suffix}",
            "english_name": f"P0 {suffix}", "width_cm": 2,
            "thickness_mm": 1, "rate_usd_per_meter": 1,
        }
    ).insert(ignore_permissions=True)

    orders = {}
    for label, board, width, length, rate in (
        ("A", "P0 أبيض", 42, 81, 11),
        ("B", "P0 أسود", 57, 93, 19),
    ):
        doc = frappe.get_doc(
            {
                "doctype": "Door Cutting Order", "customer": customer.name,
                "board_description": board, "board_length_cm": 244,
                "board_width_cm": 122, "default_edge_type": edge.name,
                "edge_color": f"P0 edge {label}", "kerf_mm": 5,
                "trim_margin_mm": 5, "optimization_time_limit_sec": 10,
                "board_rate_usd": rate, "cutting_cost_per_board_usd": 2,
                "pieces": [
                    {"piece_type": "Regular", "width_cm": width,
                     "length_cm": length, "qty": 1}
                ],
            }
        ).insert(ignore_permissions=True)
        orders[label] = {
            "name": str(doc.name), "board": board,
            "piece_name": str(doc.pieces[0].name),
            "width_cm": width, "length_cm": length,
        }
    if orders["A"]["piece_name"] == orders["B"]["piece_name"]:
        raise AssertionError("Frappe generated duplicate child names")

    # Administrator can pass document-level checks while its boot route catalog
    # omits this DocType. Use a disposable, explicitly granted factory role.
    administrator = {
        "metadata": bool(frappe.db.exists("DocType", "Door Cutting Order")),
        "has_read": bool(frappe.has_permission("Door Cutting Order", "read", user="Administrator")),
        "can_read_route": "Door Cutting Order" in frappe.get_user("Administrator").get_can_read(),
    }
    role = frappe.get_doc({"doctype": "Role", "role_name": f"P0 Desk {suffix}",
                           "desk_access": 1}).insert(ignore_permissions=True)
    ProjectedPermissionMatrixRepository().save_role_states({str(role.name): {
        Capability.VIEW_ORDERS: True,
        Capability.VIEW_ALL_ORDERS: True,
        Capability.CREATE_ORDER: True,
        Capability.EDIT_ORDER: True,
        Capability.VIEW_COSTS: True,
        Capability.VIEW_CUTTING_PLAN: True,
        Capability.VIEW_SYSTEM_CUTTING_PLAN: True,
        Capability.PRINT_CUTTING_PLAN: True,
        Capability.VIEW_CUSTOMERS: True,
        Capability.VIEW_EDGE_BANDING_TYPES: True,
    }})
    email = f"p0-desk-{suffix}@example.com"
    password = uuid4().hex
    frappe.get_doc({"doctype": "User", "email": email, "first_name": "P0 Desk",
                    "user_type": "System User", "enabled": 1, "send_welcome_email": 0,
                    "new_password": password, MEMBERSHIP_FIELD: 1,
                    "roles": [{"role": str(role.name)}]}).insert(ignore_permissions=True)
    frappe.clear_cache(user=email)
    frappe.clear_cache(doctype="Door Cutting Order")
    frappe.set_user(email)
    test_user = {
        "metadata": bool(frappe.db.exists("DocType", "Door Cutting Order")),
        "has_read": bool(frappe.has_permission("Door Cutting Order", "read", user=email)),
        "can_read_route": "Door Cutting Order" in frappe.get_user(email).get_can_read(),
        "can_read_customer": "Customer" in frappe.get_user(email).get_can_read(),
    }
    if not all(test_user.values()):
        raise AssertionError(f"Isolated user cannot enter real DCO Form: {test_user}; Administrator: {administrator}")
    frappe.set_user("Administrator")
    frappe.db.commit()
    destination = os.environ.get("P0_FIXTURE_PATH")
    if not destination:
        raise RuntimeError("P0_FIXTURE_PATH is required in the isolated CI job")
    fixture = {"versions": versions, "customer": str(customer.name),
               "edge_type": str(edge.name), "orders": orders,
               "user": email, "password": password, "role": str(role.name),
               "route_preflight": {"administrator": administrator, "test_user": test_user}}
    Path(destination).write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    return {"versions": versions, "orders": orders,
            "route_preflight": fixture["route_preflight"]}


def cleanup() -> None:
    """Best effort disposal of records created by this job, never user records."""
    path = os.environ.get("P0_FIXTURE_PATH")
    if not path or not Path(path).is_file():
        return
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    frappe.set_user("Administrator")
    for row in fixture["orders"].values():
        frappe.delete_doc("Door Cutting Order", row["name"], force=True,
                          ignore_permissions=True)
    frappe.delete_doc("Customer", fixture["customer"], force=True,
                      ignore_permissions=True)
    frappe.delete_doc("Edge Banding Type", fixture["edge_type"], force=True,
                      ignore_permissions=True)
    frappe.delete_doc("User", fixture["user"], force=True,
                      ignore_permissions=True)
    frappe.delete_doc("Role", fixture["role"], force=True,
                      ignore_permissions=True)
    frappe.db.commit()


def audit_db() -> dict[str, object]:
    """Read committed rows in a fresh bench process, independent of Desk cache."""
    path = os.environ.get("P0_FIXTURE_PATH")
    if not path or not Path(path).is_file():
        return {"status": "NOT_TESTED", "reason": "fixture unavailable"}
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    frappe.set_user("Administrator")
    rows = {}
    for label, expected in fixture["orders"].items():
        order = frappe.get_doc("Door Cutting Order", expected["name"])
        rows[label] = {"name": order.name, "board": order.board_description,
                       "modified": str(order.modified),
                       "pieces": [{"name": piece.name, "width_cm": piece.width_cm,
                                   "length_cm": piece.length_cm} for piece in order.pieces]}
    result = {"status": "OBSERVED", "rows": rows,
              "distinct_child_names": rows["A"]["pieces"][0]["name"] != rows["B"]["pieces"][0]["name"]}
    evidence_dir = os.environ.get("P0_EVIDENCE_DIR")
    if evidence_dir:
        Path(evidence_dir).mkdir(parents=True, exist_ok=True)
        (Path(evidence_dir) / "database-audit.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
