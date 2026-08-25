from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / "almdina_erp" / "doctype" / "door_cutting_order_detail" / "door_cutting_order_detail.json"
ORDER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
SETTINGS = ROOT / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"
PLAN_PIECE = ROOT / "almdina_erp" / "doctype" / "cutting_plan_piece" / "cutting_plan_piece.json"
DOMAIN = ROOT / "almdina_erp" / "domain" / "orders" / "extra_addons.py"
ADAPTER = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "costing_adapter.py"
DOCUMENTS = ROOT / "almdina_erp" / "application" / "costing" / "financial_documents.py"
MUTATION = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_mutation_impact_policy.js"
UX = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "extra_addons" / "door_cutting_order_extra_addons_ux.js"
CSS = ROOT / "public" / "css" / "door_cutting_order_extra_addons.css"
ASSETS = ROOT / "frontend_assets.py"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_extra_is_a_fourth_door_type_but_not_a_special_shape_type() -> None:
    detail = _fields(DETAIL)
    plan = _fields(PLAN_PIECE)
    expected = "Regular\nClipped Corner\nSpecial\nExtra"
    assert detail["piece_type"]["options"] == expected
    assert plan["piece_type"]["options"] == expected

    domain = DOMAIN.read_text(encoding="utf-8")
    assert 'EXTRA_PIECE_TYPE = "Extra"' in domain
    assert "special_shape" not in domain


def test_selections_are_plain_requirements_while_price_snapshots_are_protected() -> None:
    detail = _fields(DETAIL)
    for fieldname in (
        "extra_double",
        "extra_liner",
        "extra_recessed_handle_cutout",
    ):
        assert detail[fieldname]["fieldtype"] == "Check"
        assert detail[fieldname].get("permlevel", 0) == 0

    for fieldname in (
        "extra_double_unit_price_usd",
        "extra_double_total_usd",
        "extra_liner_unit_price_usd",
        "extra_liner_total_usd",
        "extra_recessed_handle_cutout_unit_price_usd",
        "extra_recessed_handle_cutout_total_usd",
        "extra_addons_total_usd",
    ):
        assert detail[fieldname]["fieldtype"] == "Currency"
        assert detail[fieldname]["permlevel"] == 1
        assert detail[fieldname]["read_only"] == 1

    order = _fields(ORDER)
    assert order["extra_addons_total_usd"]["permlevel"] == 1


def test_factory_settings_own_three_positive_per_door_prices() -> None:
    settings = _fields(SETTINGS)
    for fieldname in (
        "default_extra_double_unit_price_usd",
        "default_extra_liner_unit_price_usd",
        "default_extra_recessed_handle_cutout_unit_price_usd",
    ):
        assert settings[fieldname]["fieldtype"] == "Currency"
        assert settings[fieldname]["non_negative"] == 1


def test_pricing_math_stays_server_side_and_customer_invoice_is_itemized() -> None:
    ux = UX.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    documents = DOCUMENTS.read_text(encoding="utf-8")
    assert "unit_price_usd *" not in ux
    assert "calculate_extra_addon_pricing" in adapter
    assert '"type": "extra_addon"' in documents
    assert "extra_double_unit_price_usd" in documents
    assert "extra_liner_unit_price_usd" in documents


def test_extra_selection_invalidates_cost_only_and_ui_is_lifecycle_safe() -> None:
    mutation = MUTATION.read_text(encoding="utf-8")
    ux = UX.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assets = ASSETS.read_text(encoding="utf-8")
    assert "PIECE_COST_ONLY_FIELDS" in mutation
    assert 'recordImpact(frm, ["cost"]' in mutation
    assert "extra_double" not in mutation.split("const PIECE_PLAN_COST_FIELDS", 1)[1].split("];", 1)[0]
    assert "registerCleanup" in ux
    assert 'event.key !== "Escape"' in ux
    assert 'aria-haspopup="menu"' in ux
    assert 'data-piece-type-option="${esc(item.value)}"' in ux
    assert "pointerover" in ux
    assert "لاينر" in ux
    assert "دبل" in ux
    assert "مسكة غطس" in ux
    assert ".dco-piece-type-flyout.is-extra-open .dco-extra-submenu" in css
    assert "@media (max-width: 720px)" in css
    assert "prefers-reduced-motion" in css
    assert "door_cutting_order_extra_addons_ux.js" in assets
    assert "door_cutting_order_extra_addons.css" in assets
    assert CSS.exists()
