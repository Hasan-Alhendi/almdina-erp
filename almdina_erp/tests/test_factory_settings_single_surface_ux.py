from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_JSON = ROOT / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"
SETTINGS_PAGE = ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js"
SETTINGS_SERVICE = ROOT / "almdina_erp" / "services" / "production_settings_service.py"
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"
MAIN_WORKSPACE = ROOT / "almdina_erp" / "workspace" / "almdina_erp" / "almdina_erp.json"

LEGACY_PRESERVED_FIELDS = {
    "enforce_stock_control",
    "default_warehouse",
    "reserve_stock_on_approval",
    "stock_consumption_point",
    "prefer_remnants_before_full_boards",
    "min_remnant_width_mm",
    "min_remnant_length_mm",
    "min_remnant_area_m2",
    "remnant_cost_policy",
    "remnant_rate_usd_per_m2",
}


def _settings_fields() -> list[dict[str, object]]:
    payload = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    return list(payload["fields"])


def test_every_active_factory_setting_is_present_in_the_unified_console() -> None:
    page_source = SETTINGS_PAGE.read_text(encoding="utf-8")
    active_fields = {
        str(field["fieldname"])
        for field in _settings_fields()
        if field.get("fieldname")
        and field.get("fieldtype") not in {"Section Break", "Column Break", "Tab Break"}
        and not int(field.get("hidden") or 0)
    }

    missing = sorted(fieldname for fieldname in active_fields if fieldname not in page_source)
    assert not missing, f"Active factory settings missing from unified console: {missing}"


def test_hidden_legacy_values_are_preserved_and_visible_read_only() -> None:
    page_source = SETTINGS_PAGE.read_text(encoding="utf-8")
    service_source = SETTINGS_SERVICE.read_text(encoding="utf-8")
    hidden_fields = {
        str(field["fieldname"])
        for field in _settings_fields()
        if field.get("fieldname")
        and field.get("fieldtype") not in {"Section Break", "Column Break", "Tab Break"}
        and int(field.get("hidden") or 0)
    }

    assert hidden_fields == LEGACY_PRESERVED_FIELDS
    assert "legacy_values" in service_source
    assert "LEGACY_PRESERVED_FIELDS" in service_source
    assert "بيانات إعدادات قديمة محفوظة" in page_source
    assert "للقراءة فقط" in page_source
    for fieldname in LEGACY_PRESERVED_FIELDS:
        assert fieldname in service_source
        assert fieldname in page_source


def test_old_native_settings_route_redirects_to_the_unified_console() -> None:
    shell_source = SHARED_SHELL.read_text(encoding="utf-8")

    assert 'FACTORY_SETTINGS_CONSOLE_ROUTE = "factory-production-settings"' in shell_source
    assert 'LEGACY_FACTORY_SETTINGS_ROUTE = "almdina-erp-settings"' in shell_source
    assert "redirectLegacyFactorySettingsRoute" in shell_source
    assert "installFactorySettingsCanonicalRedirect" in shell_source
    assert "frappe.set_route(FACTORY_SETTINGS_CONSOLE_ROUTE)" in shell_source


def test_main_workspace_factory_settings_shortcut_opens_unified_console() -> None:
    workspace = json.loads(MAIN_WORKSPACE.read_text(encoding="utf-8"))
    links = [row for row in workspace.get("links", []) if row.get("label") == "إعدادات المعمل"]
    shortcuts = [row for row in workspace.get("shortcuts", []) if row.get("label") == "إعدادات المعمل"]

    assert len(links) == 1
    assert links[0]["link_type"] == "Page"
    assert links[0]["link_to"] == "factory-production-settings"
    assert len(shortcuts) == 1
    assert shortcuts[0]["type"] == "Page"
    assert shortcuts[0]["link_to"] == "factory-production-settings"


def test_unified_console_does_not_delete_or_mutate_legacy_values() -> None:
    service_source = SETTINGS_SERVICE.read_text(encoding="utf-8")

    assert '"legacy_values": _legacy_settings_values(settings)' in service_source
    assert "def _legacy_settings_values" in service_source
    assert "LEGACY_PRESERVED_FIELDS" not in service_source.split("def _apply_values", 1)[1].split("def _print_identity_values", 1)[0]
