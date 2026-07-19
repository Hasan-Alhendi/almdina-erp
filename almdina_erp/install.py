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


ITEM_CUSTOM_FIELDS = {
    "Item": [
        {
            "fieldname": "custom_mdf_board_settings_section",
            "label": "MDF / Cutting Board Settings",
            "fieldtype": "Section Break",
            "insert_after": "stock_uom",
        },
        {
            "fieldname": "custom_is_mdf",
            "label": "Is MDF Board",
            "fieldtype": "Check",
            "insert_after": "custom_mdf_board_settings_section",
            "default": "0",
        },
        {
            "fieldname": "custom_board_length_mm",
            "label": "Board Length (MM)",
            "fieldtype": "Float",
            "insert_after": "custom_is_mdf",
            "non_negative": 1,
        },
        {
            "fieldname": "custom_board_width_mm",
            "label": "Board Width (MM)",
            "fieldtype": "Float",
            "insert_after": "custom_board_length_mm",
            "non_negative": 1,
        },
        {
            "fieldname": "custom_board_thickness_mm",
            "label": "Board Thickness (MM)",
            "fieldtype": "Float",
            "insert_after": "custom_board_width_mm",
            "non_negative": 1,
        },
        {
            "fieldname": "custom_board_color",
            "label": "Board Color",
            "fieldtype": "Data",
            "insert_after": "custom_board_thickness_mm",
        },
        {
            "fieldname": "custom_board_material",
            "label": "Board Material",
            "fieldtype": "Data",
            "insert_after": "custom_board_color",
        },
    ]
}


def after_install() -> None:
    """Install only the v1.0 baseline master data required by the SRS."""
    create_custom_fields(ITEM_CUSTOM_FIELDS, update=True)
    seed_edge_banding_types()


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
