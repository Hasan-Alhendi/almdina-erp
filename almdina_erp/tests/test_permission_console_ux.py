from __future__ import annotations

from pathlib import Path

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    capability_catalog_payload,
)
from almdina_erp.almdina_erp.application.security.permission_transfer import (
    build_permission_export,
    parse_permission_export,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
)


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js"


def test_role_search_is_inside_one_searchable_dropdown() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'role="combobox"' in source
    assert "apc-role-picker" in source
    assert "apc-role-menu" in source
    assert "apc-role-option" in source
    assert "handleRolePickerKeydown" in source
    assert "ابحث واختر دورًا" in source
    assert "apc-role-search" not in source
    assert "apc-role-select" not in source


def test_section_and_global_select_all_controls_are_present() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "apc-select-all-group" in source
    assert "apc-select-all-global" in source
    assert "onGroupBulkToggle" in source
    assert "onGlobalBulkToggle" in source
    assert "تحديد الكل للكل" in source
    assert "إلغاء تحديد الكل للكل" in source
    assert "syncBulkControls" in source


def test_permission_console_never_silently_hides_server_capabilities() -> None:
    source = PAGE.read_text(encoding="utf-8")
    groups = capability_catalog_payload()
    rendered_keys = [
        capability["key"]
        for group in groups
        for capability in group["capabilities"]
    ]

    assert set(rendered_keys) == ALL_CAPABILITIES
    assert len(rendered_keys) == len(set(rendered_keys))
    assert "completeCatalog" in source
    assert "صلاحيات أخرى" in source
    assert "صلاحيات موجودة في الخادم ولم تكن مصنفة" in source
    assert "Frappe: {0}" in source


def test_json_export_import_round_trip_and_browser_validation() -> None:
    source = PAGE.read_text(encoding="utf-8")
    state = {
        Capability.VIEW_ORDERS: True,
        Capability.CREATE_ORDER: True,
        Capability.PRINT_MEASUREMENTS: True,
    }
    exported = build_permission_export(role="Order Entry", state=state)
    imported = parse_permission_export(exported)

    assert imported["source_role"] == "Order Entry"
    assert imported["capabilities"][Capability.VIEW_ORDERS] is True
    assert imported["capabilities"][Capability.CREATE_ORDER] is True
    assert imported["capabilities"][Capability.PRINT_MEASUREMENTS] is True

    assert "export_role_permissions" in source
    assert "preview_permission_import" in source
    assert "JSON.parse(payload)" in source
    assert 'input.value = ""' in source
    assert "URL.createObjectURL" in source
    assert "URL.revokeObjectURL" in source
    assert "لن يتغير الدور قبل الحفظ" in source
