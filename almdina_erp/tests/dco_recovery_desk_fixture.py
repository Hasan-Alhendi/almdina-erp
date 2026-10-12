from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete as run_setup_wizard

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
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


def _permission_rows(table: str, doctype: str, roles: list[str]) -> list[dict[str, object]]:
    permission_fields = (
        "read",
        "select",
        "create",
        "write",
        "delete",
        "submit",
        "cancel",
        "amend",
        "print",
        "email",
        "report",
        "export",
        "import",
        "share",
    )
    meta = frappe.get_meta(table)
    fields = ["role", "permlevel", *(name for name in permission_fields if meta.has_field(name))]
    if meta.has_field("view_customers"):
        fields.append("view_customers")
    return [
        dict(row)
        for row in frappe.get_all(
            table,
            filters={"parent": doctype, "role": ["in", roles]},
            fields=fields,
            order_by="permlevel asc",
        )
    ]


def _assert_creator_permission_contract(
    role: str,
    creator: str,
    customer: str,
    existing_order: str,
) -> dict[str, object]:
    """Verify the real DocPerm projection and lookup access of CREATE_ORDER."""
    from frappe.permissions import get_role_permissions, has_permission

    dco_rights = get_role_permissions("Door Cutting Order", user=creator)
    customer_rights = get_role_permissions("Customer", user=creator)
    customer_field = frappe.get_meta("Door Cutting Order").get_field("customer")
    from frappe.permissions import get_roles

    business_roles = sorted(get_roles(creator, with_standard=False))
    if business_roles != [role]:
        frappe.throw(f"Unexpected non-standard roles on CREATE_ORDER fixture: {business_roles}")
    effective_roles = sorted(get_roles(creator))

    dco_docperm_rows = _permission_rows("DocPerm", "Door Cutting Order", effective_roles)
    dco_custom_docperm_rows = _permission_rows(
        "Custom DocPerm", "Door Cutting Order", effective_roles
    )
    customer_docperm_rows = _permission_rows("DocPerm", "Customer", effective_roles)
    customer_custom_docperm_rows = _permission_rows("Custom DocPerm", "Customer", effective_roles)
    dco_field_permission_rows = [
        row for row in (*dco_docperm_rows, *dco_custom_docperm_rows)
        if int(row.get("permlevel") or 0) > 0
    ]
    customer_field_permission_rows = [
        row for row in (*customer_docperm_rows, *customer_custom_docperm_rows)
        if int(row.get("permlevel") or 0) > 0
    ]
    field_contract = {
        "permlevel": int(customer_field.permlevel or 0),
        "hidden": bool(customer_field.hidden),
        "read_only": bool(customer_field.read_only),
    }
    if field_contract != {"permlevel": 0, "hidden": False, "read_only": False}:
        frappe.throw(f"Unexpected DCO Customer field metadata: {field_contract}")

    if not (dco_rights.read and dco_rights.create) or dco_rights.write:
        frappe.throw(f"CREATE_ORDER DCO projection is not create-only: {dict(dco_rights)}")
    if (
        not (customer_rights.read and customer_rights.select)
        or customer_rights.create
        or customer_rights.write
    ):
        frappe.throw(
            f"CREATE_ORDER Customer lookup projection is incorrect: {dict(customer_rights)}"
        )
    field_rights = (
        "read",
        "select",
        "create",
        "write",
        "delete",
        "submit",
        "cancel",
        "amend",
        "print",
        "email",
        "report",
        "export",
        "import",
        "share",
    )
    for doctype, rows in (
        ("Door Cutting Order", dco_field_permission_rows),
        ("Customer", customer_field_permission_rows),
    ):
        if any(bool(row.get(right)) for row in rows for right in field_rights):
            frappe.throw(
                f"CREATE_ORDER user has unexpected {doctype} field grants: {rows}"
            )
    customer_view_grants = [
        row
        for row in customer_custom_docperm_rows
        if int(row.get("permlevel") or 0) == 0 and bool(row.get("view_customers"))
    ]
    if customer_view_grants:
        frappe.throw(
            "CREATE_ORDER fixture received an effective VIEW_CUSTOMERS business grant "
            f"through assigned roles: {customer_view_grants}"
        )
    creator_can_create_dco = bool(has_permission("Door Cutting Order", "create", user=creator))
    if not creator_can_create_dco:
        frappe.throw("CREATE_ORDER fixture lacks Frappe's server-side DCO create permission.")
    if not has_permission("Customer", "read", customer, user=creator):
        frappe.throw("CREATE_ORDER user cannot read the fixture Customer for Link selection.")
    if has_permission("Door Cutting Order", "write", existing_order, user=creator):
        frappe.throw("CREATE_ORDER user unexpectedly has write access to an existing DCO.")

    administrator_access = {
        "customer_read": bool(has_permission("Customer", "read", customer, user="Administrator")),
        "existing_dco_write": bool(
            has_permission("Door Cutting Order", "write", existing_order, user="Administrator")
        ),
    }
    if not all(administrator_access.values()):
        frappe.throw(f"Administrator comparison did not have expected access: {administrator_access}")

    return {
        "creator": {
            "dco_effective_p0": {
                right: bool(dco_rights.get(right)) for right in ("read", "select", "create", "write")
            },
            "non_standard_roles": business_roles,
            "customer_effective_p0": {
                right: bool(customer_rights.get(right))
                for right in ("read", "select", "create", "write")
            },
            "dco_docperm_rows": dco_docperm_rows,
            "dco_custom_docperm_rows": dco_custom_docperm_rows,
            "dco_field_permission_rows": dco_field_permission_rows,
            "customer_field_permission_rows": customer_field_permission_rows,
            "effective_roles": effective_roles,
            "business_roles": business_roles,
            "customer_docperm_rows": customer_docperm_rows,
            "customer_custom_docperm_rows": customer_custom_docperm_rows,
            "customer_field": field_contract,
            "view_customers_business_grants": customer_view_grants,
            "customer_record_read": True,
            "dco_create": creator_can_create_dco,
            "existing_dco_write": False,
        },
        "administrator": administrator_access,
    }


def _order(suffix: str, customer: str, edge_type: str) -> str:
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
                    "width_cm": 60,
                    "length_cm": 100,
                    "qty": 1,
                }
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


def create_desk_edit_recovery_fixtures() -> dict[str, object]:
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
    ProjectedPermissionMatrixRepository().save_role_state(
        str(role.name),
        {Capability.VIEW_ORDERS: True, Capability.EDIT_ORDER: True},
    )
    worker = _worker(suffix, str(role.name))

    creator_role = frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": f"DCO Recovery Creator {suffix}",
            "desk_access": 1,
        }
    )
    creator_role.insert(ignore_permissions=True)
    ProjectedPermissionMatrixRepository().save_role_state(
        str(creator_role.name),
        {Capability.CREATE_ORDER: True},
    )
    creator = _worker(f"creator-{suffix}", str(creator_role.name))

    customer = _customer(suffix)
    edge_type = _edge_type(suffix)
    route = _route(suffix, str(role.name))
    fixtures: dict[str, object] = {
        "restore": _order(f"restore-{suffix}", customer, edge_type),
        "dispatch": _order(f"dispatch-{suffix}", customer, edge_type),
        "identity_a": _order(f"identity-a-{suffix}", customer, edge_type),
        "identity_b": _order(f"identity-b-{suffix}", customer, edge_type),
        "permission": _order(f"permission-{suffix}", customer, edge_type),
        "route": route,
        "role": str(role.name),
        "worker": worker,
        "creator": creator,
        "customer": customer,
        "edge_type": edge_type,
    }
    fixtures["permission_evidence"] = _assert_creator_permission_contract(
        str(creator_role.name),
        creator,
        customer,
        str(fixtures["permission"]),
    )
    destination = os.environ.get("DCO_DESK_FIXTURE_FILE")
    if not destination:
        frappe.throw("DCO_DESK_FIXTURE_FILE must point to an isolated CI temp file.")
    Path(destination).write_text(json.dumps(fixtures), encoding="utf-8")
    return fixtures
