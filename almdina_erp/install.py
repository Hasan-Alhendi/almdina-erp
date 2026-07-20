from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


EDGE_BANDING_TYPES: tuple[tuple[str, float], ...] = (
    ("قشاط 2سم عادي", 0.5),
    ("قشاط 4سم عادي", 1.0),
    ("قشاط 2سم لميع", 1.0),
    ("قشاط 4سم لميع", 2.0),
    ("قشاط 2سم عادي يدوي", 1.0),
    ("قشاط 4سم عادي يدوي", 2.0),
    ("قشاط 2سم ذهبي", 1.25),
    ("قشاط 4سم ذهبي", 2.5),
    ("قشاط 2سم ذهبي يدوي", 2.5),
    ("قشاط 4سم ذهبي يدوي", 5.0),
    ("قشاط 2سم لميع يدوي", 2.0),
    ("قشاط 4سم لميع يدوي", 4.0),
)

ROLES = (
    "Order Entry",
    "Cutting Operator",
    "Edge Operator",
    "Production Manager",
    "Stock Manager",
    "Accounts Management",
)

ITEM_CUSTOM_FIELDS = {
    "Item": [
        {"fieldname": "custom_mdf_board_settings_section", "label": "MDF / Cutting Board Settings", "fieldtype": "Section Break", "insert_after": "stock_uom"},
        {"fieldname": "custom_is_mdf", "label": "Is MDF Board", "fieldtype": "Check", "insert_after": "custom_mdf_board_settings_section", "default": "0"},
        {"fieldname": "custom_board_length_mm", "label": "Board Length (MM)", "fieldtype": "Float", "insert_after": "custom_is_mdf", "non_negative": 1},
        {"fieldname": "custom_board_width_mm", "label": "Board Width (MM)", "fieldtype": "Float", "insert_after": "custom_board_length_mm", "non_negative": 1},
        {"fieldname": "custom_board_thickness_mm", "label": "Board Thickness (MM)", "fieldtype": "Float", "insert_after": "custom_board_width_mm", "non_negative": 1},
        {"fieldname": "custom_board_color", "label": "Board Color", "fieldtype": "Data", "insert_after": "custom_board_thickness_mm"},
        {"fieldname": "custom_board_material", "label": "Board Material", "fieldtype": "Data", "insert_after": "custom_board_color"},
    ]
}

DEFAULT_ROUTING_NAME = "MDF Cutting Baseline v1"


def sync_setup() -> None:
    create_custom_fields(ITEM_CUSTOM_FIELDS, update=True)
    seed_roles()
    seed_edge_banding_types()
    seed_default_routing()
    seed_settings_defaults()


def after_install() -> None:
    """Install the exact v1.0 baseline setup required by the SRS."""
    sync_setup()


def after_migrate() -> None:
    """Keep required roles/master data/custom fields present after upgrades."""
    sync_setup()


def seed_roles() -> None:
    for role_name in ROLES:
        if frappe.db.exists("Role", role_name):
            continue
        frappe.get_doc({"doctype": "Role", "role_name": role_name}).insert(ignore_permissions=True)


def seed_edge_banding_types() -> None:
    for edge_type_name, rate in EDGE_BANDING_TYPES:
        if frappe.db.exists("Edge Banding Type", edge_type_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Edge Banding Type",
                "edge_type_name": edge_type_name,
                "rate_usd_per_meter": rate,
                "disabled": 0,
            }
        ).insert(ignore_permissions=True)


def seed_default_routing() -> None:
    if frappe.db.exists("Production Routing", DEFAULT_ROUTING_NAME):
        return

    routing = frappe.new_doc("Production Routing")
    routing.routing_name = DEFAULT_ROUTING_NAME
    routing.disabled = 0
    routing.append("stages", {"sequence": 10, "stage_type": "Review / Preparation", "required": 1, "auto_complete_if_not_applicable": 1})
    routing.append("stages", {"sequence": 20, "stage_type": "Cutting", "required": 1, "auto_complete_if_not_applicable": 0})
    routing.append("stages", {"sequence": 30, "stage_type": "Edge Banding", "required": 1, "auto_complete_if_not_applicable": 1})
    routing.insert(ignore_permissions=True)


def seed_settings_defaults() -> None:
    settings = frappe.get_single("Almdina ERP Settings")
    changed = False
    defaults = {
        "default_kerf_mm": 3,
        "default_trim_margin_mm": 5,
        "default_cutting_cost_per_board_usd": 1,
        "default_packing_mode": "Auto",
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
