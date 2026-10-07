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
PLAN_ADAPTER = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "plan_adapter.py"
DOCUMENTS = ROOT / "almdina_erp" / "application" / "costing" / "financial_documents.py"
MUTATION = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_mutation_impact_policy.js"
OPERATOR = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_operator_ux.js"
UX = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "extra_addons" / "door_cutting_order_extra_addons_ux.js"
CSS = ROOT / "public" / "css" / "door_cutting_order_extra_addons.css"
ASSETS = ROOT / "frontend_assets.py"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_piece_type_contract_has_only_four_supported_types() -> None:
    expected = "Regular\nClipped Corner\nL-Shaped Corner\nSpecial"
    assert _fields(DETAIL)["piece_type"]["options"] == expected
    assert _fields(PLAN_PIECE)["piece_type"]["options"] == expected
    domain = DOMAIN.read_text(encoding="utf-8")
    assert "EXTRA_PIECE_TYPE" not in domain


def test_selections_are_requirements_while_price_snapshots_are_protected() -> None:
    detail = _fields(DETAIL)
    flags = (
        "extra_double",
        "extra_full_door_double",
        "extra_liner",
        "extra_back_groove",
        "extra_recessed_handle_cutout",
    )
    for fieldname in flags:
        assert detail[fieldname]["fieldtype"] == "Check"
        assert detail[fieldname].get("permlevel", 0) == 0

    for fieldname in (
        "extra_double_unit_price_usd",
        "extra_double_total_usd",
        "extra_full_door_double_unit_price_usd",
        "extra_full_door_double_total_usd",
        "extra_liner_unit_price_usd",
        "extra_liner_total_usd",
        "extra_back_groove_unit_price_usd",
        "extra_back_groove_total_usd",
        "extra_recessed_handle_cutout_unit_price_usd",
        "extra_recessed_handle_cutout_total_usd",
        "extra_addons_total_usd",
    ):
        assert detail[fieldname]["fieldtype"] == "Currency"
        assert detail[fieldname]["permlevel"] == 1
        assert detail[fieldname]["read_only"] == 1
    assert _fields(ORDER)["extra_addons_total_usd"]["permlevel"] == 1


def test_factory_settings_keep_five_per_door_prices() -> None:
    settings = _fields(SETTINGS)
    for fieldname in (
        "default_extra_double_unit_price_usd",
        "default_extra_full_door_double_unit_price_usd",
        "default_extra_liner_unit_price_usd",
        "default_extra_back_groove_unit_price_usd",
        "default_extra_recessed_handle_cutout_unit_price_usd",
    ):
        assert settings[fieldname]["fieldtype"] == "Currency"
        assert settings[fieldname]["non_negative"] == 1


def test_pricing_plan_quantity_and_mutation_impacts_stay_in_their_owners() -> None:
    ux = UX.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    plan_adapter = PLAN_ADAPTER.read_text(encoding="utf-8")
    documents = DOCUMENTS.read_text(encoding="utf-8")
    mutation = MUTATION.read_text(encoding="utf-8")

    assert "unit_price_usd *" not in ux
    assert "calculate_extra_addon_pricing" in adapter
    assert "mutually_exclusive_double_addons" in adapter
    assert "physical_cut_quantity" in plan_adapter
    assert '"type": "extra_addon"' in documents
    assert 'elif piece_type == "Extra"' not in documents

    plan_fields = mutation.split("const PIECE_PLAN_COST_FIELDS", 1)[1].split("];", 1)[0]
    cost_fields = mutation.split("const PIECE_COST_ONLY_FIELDS", 1)[1].split("];", 1)[0]
    assert "extra_full_door_double" in plan_fields
    assert "extra_double" not in plan_fields
    assert "extra_liner" in cost_fields
    assert "extra_back_groove" in cost_fields


def test_measurement_table_owns_five_compact_checkbox_columns_without_popup() -> None:
    ux = UX.read_text(encoding="utf-8")
    operator = OPERATOR.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assets = ASSETS.read_text(encoding="utf-8")

    assert '<select class="dco-fast-select dco-piece-type-select"' in ux
    assert 'data-field="piece_type"' in ux
    assert 'value="Extra"' not in ux
    assert "renderAddonCell" in ux
    assert "enforceMutualExclusivity" in ux
    assert "dco-extra-submenu-flyout" not in ux
    assert "renderSubmenu" not in ux

    for fieldname in (
        "extra_double",
        "extra_full_door_double",
        "extra_liner",
        "extra_back_groove",
        "extra_recessed_handle_cutout",
    ):
        assert fieldname in operator
    assert "dco-col-addon" in operator
    assert ".dco-col-addon" in css
    assert "width: 46px" in css
    assert ".dco-extra-submenu-flyout" not in css
    assert "door_cutting_order_extra_addons_ux.js" in assets
    assert "door_cutting_order_extra_addons.css" in assets
