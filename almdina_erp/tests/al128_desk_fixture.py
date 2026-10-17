"""Isolated test-site data for the ALMADINA-128 real Desk acceptance run."""

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


def _assert_runtime_and_setup() -> dict[str, object]:
    import erpnext

    versions = {"frappe": frappe.__version__, "erpnext": erpnext.__version__}
    expected = {"frappe": "16.17.5", "erpnext": "16.17.0"}
    if versions != expected:
        frappe.throw(f"ALMADINA-128 Desk requires {expected}; found {versions}.")
    app_setup = {
        app: frappe.db.get_value("Installed Application", {"app_name": app}, "is_setup_complete")
        for app in ("frappe", "erpnext")
    }
    return {
        "versions": versions,
        "setup_complete": bool(frappe.is_setup_complete()),
        "installed_app_setup": app_setup,
        "company_count": frappe.db.count("Company"),
    }


def prepare_al128_desk_site() -> dict[str, object]:
    """Complete only the ephemeral CI site through Frappe's supported wizard."""
    frappe.set_user("Administrator")
    before = _assert_runtime_and_setup()
    if not before["setup_complete"]:
        suffix = uuid4().hex[:8]
        setup_complete(
            {
                "language": "English",
                "lang": "en",
                "country": "United States",
                "currency": "USD",
                "timezone": "UTC",
                "company_name": f"AL128 Desk Test {suffix}",
                "company_abbr": f"A{suffix[:7]}",
                "chart_of_accounts": "Standard",
                "fy_start_date": "2026-01-01",
                "fy_end_date": "2026-12-31",
                "domain": "Manufacturing",
                "setup_demo": 0,
            }
        )
        frappe.db.commit()
        frappe.clear_cache()
    after = _assert_runtime_and_setup()
    if not after["setup_complete"] or not all(after["installed_app_setup"].values()):
        frappe.throw(f"Official Setup Wizard did not complete the isolated site: {after}")
    if not after["company_count"]:
        frappe.throw("The official Setup Wizard did not create the CI test Company.")
    return {"before": before, "after": after}


def _category(doctype: str, name_field: str, parent_field: str, suffix: str) -> str:
    leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
    if leaf:
        return str(leaf)
    root = frappe.db.get_value(doctype, {"is_group": 1}, "name")
    if not root:
        root_doc = frappe.get_doc(
            {"doctype": doctype, name_field: f"AL128 Test {suffix}", "is_group": 1}
        )
        root_doc.insert(ignore_permissions=True)
        root = root_doc.name
    leaf_doc = frappe.get_doc(
        {
            "doctype": doctype,
            name_field: f"AL128 Test {suffix}",
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
            "customer_name": f"AL128 Browser {suffix}",
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
            "edge_type_name": f"AL128 Browser {suffix}",
            "english_name": f"AL128 {suffix}",
            "width_cm": 2,
            "thickness_mm": 1,
            "rate_usd_per_meter": 1,
        }
    )
    edge.insert(ignore_permissions=True)
    return str(edge.name)


def _configure_fixture_extra_rates() -> dict[str, float]:
    """Provide required commercial data only on the disposable acceptance site."""
    settings = frappe.get_single("Almdina ERP Settings")
    settings.default_extra_liner_unit_price_usd = 2.5
    settings.flags.ignore_permissions = True
    settings.flags.ignore_mandatory = True
    settings.save(ignore_permissions=True)
    liner_rate = float(
        frappe.db.get_single_value(
            "Almdina ERP Settings", "default_extra_liner_unit_price_usd"
        )
        or 0
    )
    if liner_rate <= 0:
        frappe.throw("The isolated ALMADINA-128 site requires a positive Liner fixture price.")
    return {"liner_unit_price_usd": liner_rate}


def _user(suffix: str, role: str) -> str:
    email = f"al128-{suffix}@example.com"
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": f"AL128 {suffix}",
            "user_type": "System User",
            "enabled": 1,
            "send_welcome_email": 0,
            "new_password": "al128-isolated-ci-password",
            MEMBERSHIP_FIELD: 1,
            "roles": [{"role": role}],
        }
    )
    user.insert(ignore_permissions=True)
    return str(user.name)


def _pieces(count: int, *, include_special: bool) -> list[dict[str, object]]:
    geometry = json.dumps(
        {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "template": "rectangle",
            "blank_width_cm": 60,
            "blank_length_cm": 100,
            "points": [[0, 0], [60, 0], [60, 100], [0, 100]],
            "exact": True,
        },
        separators=(",", ":"),
    )
    result = []
    for index in range(count):
        special = include_special and index == 2
        result.append(
            {
                "piece_type": "Special" if special else "Regular",
                "width_cm": 60 if special else 40 + index % 35,
                "length_cm": 100 if special else 80 + index % 75,
                "qty": 1 + index % 3,
                "notes": f"AL128 fixture piece {index + 1}",
                "extra_liner": int(index == 8),
                "edge_long_left": int(index == 0),
                "edge_width_top": int(index == 0),
                "special_shape_geometry_json": geometry if special else "",
            }
        )
    return result


def _order(customer: str, edge_type: str, count: int, *, include_special: bool) -> str:
    order = frappe.get_doc(
        {
            "doctype": "Door Cutting Order",
            "customer": customer,
            "board_description": "ALMADINA-128 isolated acceptance MDF",
            "board_length_cm": 244,
            "board_width_cm": 122,
            "order_cutting_machine": "CNC",
            "default_edge_type": edge_type,
            "edge_color": "White",
            "order_notes": f"AL128 fixture {count} pieces",
            "pieces": _pieces(count, include_special=include_special),
        }
    )
    order.insert(ignore_permissions=True)
    return str(order.name)


def create_al128_desk_fixtures() -> dict[str, object]:
    """Seed isolated orders and verify projected permissions before browser login."""
    frappe.set_user("Administrator")
    preflight = _assert_runtime_and_setup()
    if not preflight["setup_complete"]:
        frappe.throw("Run prepare_al128_desk_site before creating browser fixtures.")

    suffix = uuid4().hex[:10]
    customer = _customer(suffix)
    edge_type = _edge_type(suffix)
    bulk_edge_type = _edge_type(f"bulk-{suffix}")
    fixture_rates = _configure_fixture_extra_rates()
    edit_role = frappe.get_doc(
        {"doctype": "Role", "role_name": f"AL128 Desk Editor {suffix}", "desk_access": 1}
    )
    edit_role.insert(ignore_permissions=True)
    view_role = frappe.get_doc(
        {"doctype": "Role", "role_name": f"AL128 Desk Viewer {suffix}", "desk_access": 1}
    )
    view_role.insert(ignore_permissions=True)
    ProjectedPermissionMatrixRepository().save_role_states(
        {
            str(edit_role.name): {
                Capability.VIEW_ORDERS: True,
                Capability.EDIT_ORDER: True,
                Capability.VIEW_CUSTOMERS: True,
                Capability.VIEW_EDGE_BANDING_TYPES: True,
            },
            str(view_role.name): {
                Capability.VIEW_ORDERS: True,
                Capability.VIEW_CUSTOMERS: True,
            },
        }
    )
    editor = _user(f"editor-{suffix}", str(edit_role.name))
    viewer = _user(f"viewer-{suffix}", str(view_role.name))

    fixtures = {
        "site": frappe.local.site,
        "versions": preflight["versions"],
        "customer": customer,
        "edge_type": edge_type,
        "bulk_edge_type": bulk_edge_type,
        "fixture_rates": fixture_rates,
        "editor": editor,
        "viewer": viewer,
        "password": "al128-isolated-ci-password",
        "edit_order": _order(customer, edge_type, 10, include_special=True),
        "identity_b": _order(customer, edge_type, 10, include_special=False),
        "performance_100": _order(customer, edge_type, 100, include_special=False),
        "performance_500": _order(customer, edge_type, 500, include_special=False),
    }

    editor_dco = get_role_permissions("Door Cutting Order", user=editor)
    editor_customer = get_role_permissions("Customer", user=editor)
    editor_edge = get_role_permissions("Edge Banding Type", user=editor)
    viewer_dco = get_role_permissions("Door Cutting Order", user=viewer)
    permission_evidence = {
        "editor_dco": {right: bool(editor_dco.get(right)) for right in ("read", "write", "create")},
        "editor_customer": {right: bool(editor_customer.get(right)) for right in ("read", "select")},
        "editor_edge_type": {right: bool(editor_edge.get(right)) for right in ("read", "select")},
        "viewer_dco": {right: bool(viewer_dco.get(right)) for right in ("read", "write")},
        "server_checks": {
            "editor_can_read": bool(
                has_permission("Door Cutting Order", "read", fixtures["edit_order"], user=editor)
            ),
            "editor_can_write": bool(
                has_permission("Door Cutting Order", "write", fixtures["edit_order"], user=editor)
            ),
            "viewer_can_read": bool(
                has_permission("Door Cutting Order", "read", fixtures["edit_order"], user=viewer)
            ),
            "viewer_can_write": bool(
                has_permission("Door Cutting Order", "write", fixtures["edit_order"], user=viewer)
            ),
        },
    }
    if not all(
        (
            permission_evidence["editor_dco"]["read"],
            permission_evidence["editor_dco"]["write"],
            permission_evidence["editor_customer"]["read"],
            permission_evidence["editor_customer"]["select"],
            permission_evidence["editor_edge_type"]["read"],
            permission_evidence["editor_edge_type"]["select"],
            permission_evidence["viewer_dco"]["read"],
            not permission_evidence["viewer_dco"]["write"],
            permission_evidence["server_checks"]["editor_can_read"],
            permission_evidence["server_checks"]["editor_can_write"],
            permission_evidence["server_checks"]["viewer_can_read"],
            not permission_evidence["server_checks"]["viewer_can_write"],
        )
    ):
        frappe.throw(f"Fixture users do not match the intended live permission boundary: {permission_evidence}")

    fixtures["permission_evidence"] = permission_evidence
    frappe.db.commit()
    destination = os.environ.get("DCO_AL128_FIXTURE_FILE")
    if not destination:
        frappe.throw("DCO_AL128_FIXTURE_FILE must target runner.temp in the isolated CI job.")
    Path(destination).write_text(json.dumps(fixtures), encoding="utf-8")
    return {"fixture_count": 4, "permission_evidence": permission_evidence}
