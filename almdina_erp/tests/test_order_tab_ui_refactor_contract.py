from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
MANIFEST = ROOT / "frontend_assets.py"
LAYOUT = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_order_tab_layout_ux.js"
)
DEFAULTS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_defaults.js"
)


def test_order_schema_removes_external_reference_and_requires_edge_defaults() -> None:
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}
    order = payload["field_order"]

    assert "external_reference" not in fields
    assert "external_reference" not in order
    assert "cutting_settings_section" not in fields
    assert "cutting_settings_section" not in order
    assert fields["default_edge_type"].get("reqd") == 1
    assert fields["edge_color"].get("reqd") == 1


def test_board_and_edge_inputs_share_one_material_section() -> None:
    payload = json.loads(DOCTYPE.read_text(encoding="utf-8"))
    order = payload["field_order"]
    material_slice = order[
        order.index("board_section") : order.index("pieces_section")
    ]

    assert material_slice == [
        "board_section",
        "board_description",
        "board_length_column",
        "board_length_cm",
        "board_width_cm",
        "board_width_column",
        "default_edge_type",
        "edge_color",
    ]


def test_order_layout_presenter_is_presentation_only_and_loaded_after_operator_owner() -> None:
    manifest = MANIFEST.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    operator_asset = '"public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"'
    layout_asset = '"public/js/door_cutting_order/order_entry/door_cutting_order_order_tab_layout_ux.js"'
    keyboard_asset = '"public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js"'

    assert layout_asset in manifest
    assert manifest.index(operator_asset) < manifest.index(layout_asset) < manifest.index(keyboard_asset)
    assert "frappe.call" not in layout
    assert "frm.save" not in layout
    assert "frm.set_value" not in layout
    assert "AlmdinaOrderEdgeOptions" in layout
    assert "dco-order-intake-card" in layout
    assert "dco-material-edge-card" in layout
    assert "dco-measurements-card" in layout
    assert "autoGrowNotes" in layout


def test_arabic_labels_reflect_the_new_information_hierarchy() -> None:
    defaults = DEFAULTS.read_text(encoding="utf-8")

    assert 'order_details_section: "بيانات الطلب"' in defaults
    assert 'board_section: "المادة والقشاط"' in defaults
    assert 'default_edge_type: "نوع القشاط الافتراضي"' in defaults
    assert 'edge_color: "لون القشاط"' in defaults
    assert "cutting_settings_section" not in defaults
