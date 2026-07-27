from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


EDGE_BANDING_TYPES = (
    {"name":"قشاط 2سم عادي","english":"2cm Regular Edge","width":2,"finish":"Regular","method":"Machine","rate":0.5},
    {"name":"قشاط 4سم عادي","english":"4cm Regular Edge","width":4,"finish":"Regular","method":"Machine","rate":1.0},
    {"name":"قشاط 2سم لميع","english":"2cm Glossy Edge","width":2,"finish":"Glossy","method":"Machine","rate":1.0},
    {"name":"قشاط 4سم لميع","english":"4cm Glossy Edge","width":4,"finish":"Glossy","method":"Machine","rate":2.0},
    {"name":"قشاط 2سم عادي يدوي","english":"2cm Regular Manual Edge","width":2,"finish":"Regular","method":"Manual","rate":1.0},
    {"name":"قشاط 4سم عادي يدوي","english":"4cm Regular Manual Edge","width":4,"finish":"Regular","method":"Manual","rate":2.0},
    {"name":"قشاط 2سم ذهبي","english":"2cm Golden Edge","width":2,"finish":"Golden","method":"Machine","rate":1.25},
    {"name":"قشاط 4سم ذهبي","english":"4cm Golden Edge","width":4,"finish":"Golden","method":"Machine","rate":2.5},
    {"name":"قشاط 2سم ذهبي يدوي","english":"2cm Golden Manual Edge","width":2,"finish":"Golden","method":"Manual","rate":2.5},
    {"name":"قشاط 4سم ذهبي يدوي","english":"4cm Golden Manual Edge","width":4,"finish":"Golden","method":"Manual","rate":5.0},
    {"name":"قشاط 2سم لميع يدوي","english":"2cm Glossy Manual Edge","width":2,"finish":"Glossy","method":"Manual","rate":2.0},
    {"name":"قشاط 4سم لميع يدوي","english":"4cm Glossy Manual Edge","width":4,"finish":"Glossy","method":"Manual","rate":4.0},
)

ROLES = (
    "Order Entry",
    "Cutting Operator",
    "Edge Operator",
    "Production Manager",
    "Stock Manager",
    "Accounts Management",
    "عامل رسم",
    "عامل شريون",
    "عامل CNC",
    "عامل تقشيط",
)

# Convenience records used only by explicit administrative seed commands.
OPERATOR_USERS = (
    {"email": "drawing@almdina.local", "first_name": "عامل", "last_name": "رسم", "profile": "drawing_operator"},
    {"email": "sharyoun@almdina.local", "first_name": "عامل", "last_name": "شريون", "profile": "sharyoun_operator"},
    {"email": "cnc@almdina.local", "first_name": "عامل", "last_name": "CNC", "profile": "cnc_operator"},
    {"email": "taqsheet@almdina.local", "first_name": "عامل", "last_name": "تقشيط", "profile": "sanding_operator"},
)

ORDER_ENTRY_USERS = (
    {
        "email": "orders@almdina.local",
        "first_name": "موظف",
        "last_name": "الطلبات",
        "profile": "order_entry",
    },
)

REQUIRED_UOMS = (
    {"name": "Meter", "must_be_whole_number": 0},
)

ITEM_CUSTOM_FIELDS = {
    "Item": [
        {"fieldname":"custom_mdf_board_settings_section","label":"MDF / Cutting Board Settings","fieldtype":"Section Break","insert_after":"stock_uom"},
        {"fieldname":"custom_is_mdf","label":"Is MDF Board","fieldtype":"Check","insert_after":"custom_mdf_board_settings_section","default":"0"},
        {"fieldname":"custom_board_length_mm","label":"Board Length (MM)","fieldtype":"Float","insert_after":"custom_is_mdf","non_negative":1},
        {"fieldname":"custom_board_width_mm","label":"Board Width (MM)","fieldtype":"Float","insert_after":"custom_board_length_mm","non_negative":1},
        {"fieldname":"custom_board_thickness_mm","label":"Board Thickness (MM)","fieldtype":"Float","insert_after":"custom_board_width_mm","non_negative":1},
        {"fieldname":"custom_board_color","label":"Board Color","fieldtype":"Data","insert_after":"custom_board_thickness_mm"},
        {"fieldname":"custom_board_material","label":"Board Material","fieldtype":"Data","insert_after":"custom_board_color"},
        {"fieldname":"custom_board_rate_usd","label":"Board Rate USD","fieldtype":"Currency","insert_after":"custom_board_material","non_negative":1},
    ]
}

DEFAULT_ROUTING_NAME = "MDF Cutting Baseline v1"
EDGE_ITEM_GROUP = "Raw Material"


def sync_setup() -> None:
    create_custom_fields(ITEM_CUSTOM_FIELDS, update=True)
    seed_roles()
    seed_required_uoms()
    seed_edge_banding_types()
    seed_default_routing()
    seed_settings_defaults()
    sync_plan_recalculation_state()
    sync_dual_plan_json_backfill()


def after_install() -> None:
    sync_setup()


def after_migrate() -> None:
    sync_setup()


def seed_roles() -> None:
    for role_name in ROLES:
        if not frappe.db.exists("Role", role_name):
            frappe.get_doc({"doctype":"Role","role_name":role_name}).insert(ignore_permissions=True)


def _require_explicit_password(password: str | None) -> str:
    password = str(password or "")
    if not password:
        frappe.throw(
            "Pass password explicitly. Almdina ERP does not store a default user password in source code."
        )
    return password


def _seed_users(rows: tuple[dict, ...], password: str | None) -> list[str]:
    from almdina_erp.almdina_erp.application.security.provision_user import provision_user

    seed_roles()
    password = _require_explicit_password(password)
    results: list[str] = []
    for row in rows:
        result = provision_user(
            email=row["email"],
            profile=row["profile"],
            first_name=row["first_name"],
            last_name=row.get("last_name", ""),
            temporary_password=password,
        )
        action = "created" if result["created"] else "updated"
        results.append(f"{action}:{row['email']}")
    frappe.db.commit()
    return results


def seed_operator_users(password: str | None = None) -> list[str]:
    """Explicitly create the four shop-floor users with a runtime password."""

    return _seed_users(OPERATOR_USERS, password)


def seed_order_entry_users(password: str | None = None) -> list[str]:
    """Explicitly create the order-entry user with a runtime password."""

    return _seed_users(ORDER_ENTRY_USERS, password)


def seed_required_uoms() -> None:
    """Create UOM records that Almdina ERP references during fresh installation."""
    for row in REQUIRED_UOMS:
        uom_name = row["name"]
        if frappe.db.exists("UOM", uom_name):
            continue

        uom = frappe.new_doc("UOM")
        uom.uom_name = uom_name
        uom.must_be_whole_number = row["must_be_whole_number"]
        uom.insert(ignore_permissions=True)


def seed_edge_banding_types() -> None:
    for row in EDGE_BANDING_TYPES:
        if frappe.db.exists("Edge Banding Type", row["name"]):
            doc = frappe.get_doc("Edge Banding Type", row["name"])
        else:
            doc = frappe.new_doc("Edge Banding Type")
            doc.edge_type_name = row["name"]
        doc.english_name = row["english"]
        doc.width_cm = row["width"]
        doc.finish_type = row["finish"]
        doc.application_method = row["method"]
        doc.consumption_uom = "Meter"
        doc.rate_usd_per_meter = row["rate"]
        doc.disabled = 0
        doc.save(ignore_permissions=True)


def seed_edge_banding_items(item_group: str = EDGE_ITEM_GROUP) -> list[str]:
    """Create and link a stock Item for every enabled Edge Banding Type.

    Call explicitly, e.g.:
      bench --site site1.local execute almdina_erp.install.seed_edge_banding_items
    """
    results: list[str] = []

    for name in frappe.get_all("Edge Banding Type", filters={"disabled": 0}, pluck="name"):
        edge = frappe.get_doc("Edge Banding Type", name)
        if edge.item_code and frappe.db.exists("Item", edge.item_code):
            continue

        item_code = edge.edge_type_name
        if not frappe.db.exists("Item", item_code):
            item = frappe.new_doc("Item")
            item.item_code = item_code
            item.item_name = edge.edge_type_name
            item.item_group = item_group
            item.stock_uom = edge.consumption_uom or "Meter"
            item.is_stock_item = 1
            item.description = edge.english_name or edge.edge_type_name
            item.insert(ignore_permissions=True)
            results.append(f"created:{item_code}")

        edge.item_code = item_code
        edge.save(ignore_permissions=True)
        results.append(f"linked:{name}")

    frappe.db.commit()
    return results


def seed_default_routing() -> None:
    if frappe.db.exists("Production Routing", DEFAULT_ROUTING_NAME):
        return
    routing = frappe.new_doc("Production Routing")
    routing.routing_name = DEFAULT_ROUTING_NAME
    routing.disabled = 0
    routing.append("stages", {"sequence":10,"stage_type":"Review / Preparation","required":1,"auto_complete_if_not_applicable":1})
    routing.append("stages", {"sequence":20,"stage_type":"Cutting","required":1,"auto_complete_if_not_applicable":0})
    routing.append("stages", {"sequence":30,"stage_type":"Edge Banding","required":1,"auto_complete_if_not_applicable":1})
    routing.insert(ignore_permissions=True)


def seed_settings_defaults() -> None:
    settings = frappe.get_single("Almdina ERP Settings")
    changed = False
    defaults = {
        "default_kerf_mm": 3,
        "default_trim_margin_mm": 5,
        "default_cutting_cost_per_board_usd": 1,
        "default_packing_mode": "Auto Pro",
        "default_cutting_machine_type": "Auto",
        "default_optimization_time_limit_sec": 10,
        "optimal_search_piece_limit": 40,
        "default_production_routing": DEFAULT_ROUTING_NAME,
        "stock_consumption_point": "Cutting Start",
        "prefer_remnants_before_full_boards": 1,
        "min_remnant_width_mm": 300,
        "min_remnant_length_mm": 300,
        "min_remnant_area_m2": 0.09,
        "remnant_cost_policy": "Zero",
    }
    for fieldname, value in defaults.items():
        if settings.get(fieldname) in (None, ""):
            settings.set(fieldname, value)
            changed = True
    if changed:
        settings.save(ignore_permissions=True)


def sync_plan_recalculation_state() -> None:
    """Keep existing valid plans usable after adding the fast-save freshness flag."""
    try:
        if not frappe.db.table_exists("Door Cutting Order"):
            return
        if not frappe.db.has_column("Door Cutting Order", "plan_needs_recalculation"):
            return
        frappe.db.sql(
            """
            update `tabDoor Cutting Order`
               set plan_needs_recalculation = case
                    when coalesce(cutting_plan_json, '') <> '' then 0
                    else 1
               end
            """
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Almdina plan freshness backfill")


def sync_dual_plan_json_backfill() -> None:
    """Copy existing cutting plans into system_plan_json after the dual-plan fields land."""
    try:
        if not frappe.db.table_exists("Door Cutting Order"):
            return
        if not frappe.db.has_column("Door Cutting Order", "system_plan_json"):
            return
        frappe.db.sql(
            """
            update `tabDoor Cutting Order`
               set system_plan_json = cutting_plan_json
             where coalesce(system_plan_json, '') = ''
               and coalesce(cutting_plan_json, '') <> ''
            """
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Almdina dual-plan JSON backfill")
