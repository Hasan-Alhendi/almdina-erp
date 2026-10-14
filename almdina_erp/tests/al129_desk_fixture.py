"""Isolated, pinned-runtime fixtures for the ALMADINA-129 Desk acceptance case."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
from frappe.permissions import get_role_permissions, has_permission

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_membership import (
    MEMBERSHIP_FIELD,
)


def _verify_runtime() -> dict[str, object]:
    import erpnext

    versions = {"frappe": frappe.__version__, "erpnext": erpnext.__version__}
    expected = {"frappe": "16.17.5", "erpnext": "16.17.0"}
    if versions != expected:
        frappe.throw(f"ALMADINA-129 Desk requires {expected}; found {versions}.")
    installed = {
        app: bool(
            frappe.db.get_value(
                "Installed Application", {"app_name": app}, "is_setup_complete"
            )
        )
        for app in ("frappe", "erpnext")
    }
    return {
        "versions": versions,
        "setup_complete": bool(frappe.is_setup_complete()),
        "installed_app_setup": installed,
        "company_count": frappe.db.count("Company"),
    }


def prepare_al129_desk_site() -> dict[str, object]:
    """Complete the disposable CI site using Frappe's supported Setup Wizard."""
    frappe.set_user("Administrator")
    before = _verify_runtime()
    if not before["setup_complete"]:
        suffix = uuid4().hex[:8]
        setup_complete(
            {
                "language": "English",
                "lang": "en",
                "country": "United States",
                "currency": "USD",
                "timezone": "UTC",
                "company_name": f"AL129 Desk Test {suffix}",
                "company_abbr": f"N{suffix[:6]}",
                "chart_of_accounts": "Standard",
                "fy_start_date": "2026-01-01",
                "fy_end_date": "2026-12-31",
                "domain": "Manufacturing",
                "setup_demo": 0,
            }
        )
        frappe.db.commit()
        frappe.clear_cache()
    after = _verify_runtime()
    if (
        not after["setup_complete"]
        or not all(after["installed_app_setup"].values())
        or not after["company_count"]
    ):
        frappe.throw(f"The Frappe Setup Wizard did not complete this isolated site: {after}")
    return {"before": before, "after": after}


def _category(doctype: str, name_field: str, parent_field: str, suffix: str) -> str:
    leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
    if leaf:
        return str(leaf)
    root = frappe.db.get_value(doctype, {"is_group": 1}, "name")
    if not root:
        root_doc = frappe.get_doc(
            {"doctype": doctype, name_field: f"AL129 {suffix}", "is_group": 1}
        )
        root_doc.insert(ignore_permissions=True)
        root = root_doc.name
    leaf_doc = frappe.get_doc(
        {
            "doctype": doctype,
            name_field: f"AL129 {suffix}",
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
            "customer_name": f"AL129 Desk {suffix}",
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
            "edge_type_name": f"AL129 Desk {suffix}",
            "english_name": f"AL129 {suffix}",
            "width_cm": 2,
            "thickness_mm": 1,
            "rate_usd_per_meter": 1,
        }
    )
    edge.insert(ignore_permissions=True)
    return str(edge.name)


def _create_user(email: str, role: str, password: str) -> None:
    frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": "AL129 Desk",
            "user_type": "System User",
            "enabled": 1,
            "send_welcome_email": 0,
            "new_password": password,
            MEMBERSHIP_FIELD: 1,
            "roles": [{"role": role}],
        }
    ).insert(ignore_permissions=True)


def create_al129_desk_fixtures() -> dict[str, object]:
    """Create only the records and dynamic permission needed by the real Desk test."""
    frappe.set_user("Administrator")
    setup = _verify_runtime()
    if not setup["setup_complete"] or not all(setup["installed_app_setup"].values()):
        frappe.throw("Run prepare_al129_desk_site before creating browser fixtures.")

    suffix = uuid4().hex[:10]
    customer = _customer(suffix)
    edge_type = _edge_type(suffix)
    role_name = f"AL129 Desk Create and Recover {suffix}"
    role = frappe.get_doc(
        {"doctype": "Role", "role_name": role_name, "desk_access": 1}
    )
    role.insert(ignore_permissions=True)
    write_role = frappe.get_doc(
        {"doctype": "Role", "role_name": f"AL129 Desk Create Edit {suffix}", "desk_access": 1}
    )
    write_role.insert(ignore_permissions=True)
    create_capabilities = {
        Capability.CREATE_ORDER: True,
        Capability.VIEW_ORDERS: True,
        Capability.VIEW_CUSTOMERS: True,
        Capability.VIEW_EDGE_BANDING_TYPES: True,
    }
    ProjectedPermissionMatrixRepository().save_role_states(
        {
            str(role.name): create_capabilities,
            str(write_role.name): {
                **create_capabilities,
                Capability.EDIT_ORDER: True,
            },
        }
    )
    email = f"al129-{suffix}@example.com"
    password = uuid4().hex
    _create_user(email, str(role.name), password)
    second_email = f"al129-second-{suffix}@example.com"
    _create_user(second_email, str(role.name), password)
    write_email = f"al129-write-{suffix}@example.com"
    _create_user(write_email, str(write_role.name), password)
    frappe.clear_cache(user=email)
    frappe.clear_cache(user=write_email)
    frappe.clear_cache(doctype="Door Cutting Order")
    frappe.local.role_permissions = {}
    if hasattr(frappe.local, "almdina_matrix_capabilities"):
        del frappe.local.almdina_matrix_capabilities

    dco_permissions = get_role_permissions("Door Cutting Order", user=email)
    write_dco_permissions = get_role_permissions("Door Cutting Order", user=write_email)
    customer_permissions = get_role_permissions("Customer", user=email)
    edge_permissions = get_role_permissions("Edge Banding Type", user=email)
    evidence = {
        "create": bool(dco_permissions.get("create")),
        "read": bool(dco_permissions.get("read")),
        "customer_read": bool(customer_permissions.get("read")),
        "customer_select": bool(customer_permissions.get("select")),
        "edge_type_read": bool(edge_permissions.get("read")),
        "edge_type_select": bool(edge_permissions.get("select")),
        "server_can_create": bool(
            has_permission("Door Cutting Order", "create", user=email)
        ),
        "server_can_read": bool(
            has_permission("Door Cutting Order", "read", user=email)
        ),
        "server_can_select_customer": bool(
            has_permission("Customer", "read", user=email)
        ),
        "server_can_select_edge_type": bool(
            has_permission("Edge Banding Type", "read", user=email)
        ),
    }
    if not all(evidence.values()):
        frappe.throw(f"The dynamic recovery user lacks required native permissions: {evidence}")
    permission_differential = {
        "create_only": {
            "create": bool(dco_permissions.get("create")),
            "read": bool(dco_permissions.get("read")),
            "write": bool(dco_permissions.get("write")),
        },
        "create_and_edit": {
            "create": bool(write_dco_permissions.get("create")),
            "read": bool(write_dco_permissions.get("read")),
            "write": bool(write_dco_permissions.get("write")),
        },
    }
    if (
        not permission_differential["create_only"]["create"]
        or not permission_differential["create_only"]["read"]
        or permission_differential["create_only"]["write"]
        or not all(permission_differential["create_and_edit"].values())
    ):
        frappe.throw(f"AL129 customer permission differential is invalid: {permission_differential}")

    settings = frappe.get_single("Almdina ERP Settings")
    settings.default_extra_liner_unit_price_usd = max(
        float(settings.default_extra_liner_unit_price_usd or 0), 2.5
    )
    settings.flags.ignore_permissions = True
    settings.save(ignore_permissions=True)

    fixture = {
        "site": frappe.local.site,
        "versions": setup["versions"],
        "user": email,
        "second_user": second_email,
        "write_user": write_email,
        "password": password,
        "customer": customer,
        "edge_type": edge_type,
        "permission_evidence": evidence,
        "permission_differential": permission_differential,
    }
    frappe.db.commit()
    destination = os.environ.get("DCO_AL129_FIXTURE_FILE")
    if not destination:
        frappe.throw("DCO_AL129_FIXTURE_FILE must point to runner.temp in this isolated CI job.")
    Path(destination).write_text(json.dumps(fixture), encoding="utf-8")
    return {
        "site": frappe.local.site,
        "versions": setup["versions"],
        "permission_evidence": evidence,
        "permission_differential": permission_differential,
    }
