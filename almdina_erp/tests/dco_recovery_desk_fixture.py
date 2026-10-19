from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete as run_setup_wizard

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.shop_floor_authorization import (
    assert_enabled_user_has_role,
)
from almdina_erp.almdina_erp.infrastructure.frappe.workforce_membership import (
    MEMBERSHIP_FIELD,
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


def _route(suffix: str, operational_role: str) -> str:
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
                    "operational_role": operational_role,
                    "required": 1,
                    "is_planning_stage": 1,
                }
            ],
        }
    )
    route.insert(ignore_permissions=True)
    return str(route.name)


def _worker(suffix: str, role: str) -> str:
    email = f"dco-recovery-{suffix}@example.com"
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": f"DCO Recovery {suffix}",
            "user_type": "System User",
            "enabled": 1,
            "send_welcome_email": 0,
            "new_password": "dco-test-worker-password",
            MEMBERSHIP_FIELD: 1,
            "roles": [{"role": role}],
        }
    )
    user.insert(ignore_permissions=True)
    assert_enabled_user_has_role(str(user.name), role)
    return str(user.name)


def _order(suffix: str, customer: str, edge_type: str, *, piece_count: int = 1) -> str:
    order = frappe.get_doc(
        {
            "doctype": "Door Cutting Order",
            "customer": customer,
            "board_description": "Recovery browser fixture MDF",
            "board_length_cm": 244,
            "board_width_cm": 122,
            "order_cutting_machine": "CNC",
            "default_edge_type": edge_type,
            "edge_color": "White",
            "order_notes": f"Official baseline {suffix}",
            "pieces": [
                {
                    "piece_type": "Regular",
                    "width_cm": 60 + index,
                    "length_cm": 100,
                    "qty": 1,
                    "notes": f"Official piece {index + 1}",
                }
                for index in range(piece_count)
            ],
        }
    )
    order.insert(ignore_permissions=True)
    return str(order.name)


def _complete_setup_wizard(suffix: str) -> dict[str, object]:
    """Use the official wizard stages when the isolated test site is incomplete."""
    frappe.set_user("Administrator")
    if not frappe.is_setup_complete():
        args = {
            "language": "English",
            "lang": "en",
            "country": "United States",
            "currency": "USD",
            "timezone": "America/Los_Angeles",
            "company_name": f"DCO Recovery Test {suffix}",
            "company_abbr": f"DR{suffix[:6]}",
            "chart_of_accounts": "Standard",
            "fy_start_date": "2026-01-01",
            "fy_end_date": "2026-12-31",
            "domain": "Manufacturing",
            "setup_demo": 0,
        }
        result = run_setup_wizard(args)
        frappe.db.commit()
        frappe.clear_cache()
        if getattr(frappe.local, "request_cache", None) is not None:
            frappe.local.request_cache.clear()
    else:
        result = {"status": "already_complete"}

    app_states = {
        app_name: frappe.db.get_value(
            "Installed Application", {"app_name": app_name}, "is_setup_complete"
        )
        for app_name in ("frappe", "erpnext")
    }
    if not frappe.is_setup_complete() or not all(app_states.values()):
        frappe.throw(
            f"Official Setup Wizard did not complete Frappe and ERPNext: {app_states}; result={result}"
        )
    if frappe.db.count("Company") == 0:
        frappe.throw("Official Setup Wizard did not create the required test Company.")
    return {"setup_result": result, "installed_app_setup": app_states}


def assert_desk_test_site_preflight() -> dict[str, object]:
    """Fail before browser startup unless the pinned runtimes and site setup are real."""
    versions = {
        "frappe": getattr(frappe, "__version__", "unknown"),
    }
    try:
        import erpnext

        versions["erpnext"] = getattr(erpnext, "__version__", "unknown")
    except ImportError:
        versions["erpnext"] = "not installed"
    expected = {"frappe": "16.17.5", "erpnext": "16.17.0"}
    if versions != expected:
        frappe.throw(f"Desk certification requires pinned versions {expected}; found {versions}.")

    app_states = {
        app_name: frappe.db.get_value(
            "Installed Application", {"app_name": app_name}, "is_setup_complete"
        )
        for app_name in ("frappe", "erpnext")
    }
    return {
        "versions": versions,
        "setup_complete": bool(frappe.is_setup_complete()),
        "installed_app_setup": app_states,
        "administrator_enabled": bool(
            frappe.db.get_value("User", "Administrator", "enabled")
        ),
        "company_count": frappe.db.count("Company"),
    }


def prepare_desk_test_site() -> dict[str, object]:
    """Certify exact app versions and complete an incomplete site officially."""
    preflight = assert_desk_test_site_preflight()
    if not preflight["setup_complete"]:
        suffix = uuid4().hex[:10]
        _complete_setup_wizard(suffix)
    result = assert_desk_test_site_preflight()
    if not result["setup_complete"] or not all(result["installed_app_setup"].values()):
        frappe.throw(f"Desk test site setup is incomplete after official wizard: {result}")
    if not result["administrator_enabled"]:
        frappe.throw("Administrator is disabled in the isolated Desk test site.")
    return result


def create_desk_edit_recovery_fixtures() -> dict[str, str]:
    """Create isolated real Frappe records used only by Desk browser CI."""

    frappe.set_user("Administrator")
    suffix = uuid4().hex[:10]
    site_state = assert_desk_test_site_preflight()
    if not site_state["setup_complete"]:
        frappe.throw("Run prepare_desk_test_site() before creating Desk recovery fixtures.")
    role = frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": f"DCO Recovery {suffix}",
            "desk_access": 1,
        }
    )
    role.insert(ignore_permissions=True)
    FrappePermissionMatrixRepository().save_role_state(
        str(role.name),
        {Capability.VIEW_ORDERS: True, Capability.EDIT_ORDER: True},
    )
    worker = _worker(suffix, str(role.name))
    replacement_worker = _worker(f"replacement-{suffix}", str(role.name))
    customer = _customer(suffix)
    edge_type = _edge_type(suffix)
    route = _route(suffix, str(role.name))
    fixtures = {
        "restore": _order(f"restore-{suffix}", customer, edge_type),
        "dispatch": _order(f"dispatch-{suffix}", customer, edge_type),
        "identity_a": _order(f"identity-a-{suffix}", customer, edge_type),
        "identity_b": _order(f"identity-b-{suffix}", customer, edge_type),
        "permission": _order(f"permission-{suffix}", customer, edge_type),
        "route": route,
        "role": str(role.name),
        "worker": worker,
        "replacement_worker": replacement_worker,
        "edge_type": edge_type,
    }
    for scenario in (
        "rows_restart", "external_conflict", "save_conflict", "two_tabs",
        "internal_checkpoint", "late_restore", "pending_checkpoint", "assignment",
    ):
        fixtures[scenario] = _order(
            f"{scenario}-{suffix}", customer, edge_type,
            piece_count=3 if scenario == "rows_restart" else 1,
        )
    destination = os.environ.get("DCO_DESK_FIXTURE_FILE")
    if not destination:
        frappe.throw("DCO_DESK_FIXTURE_FILE must point to an isolated CI temp file.")
    Path(destination).write_text(json.dumps(fixtures), encoding="utf-8")
    return fixtures
