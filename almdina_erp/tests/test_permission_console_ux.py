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
CONTROLLER = ROOT / "public" / "js" / "factory_permissions" / "controller.js"
API = ROOT / "public" / "js" / "factory_permissions" / "api.js"
VIEW_MODEL = ROOT / "public" / "js" / "factory_permissions" / "view_model.js"
RENDERER = ROOT / "public" / "js" / "factory_permissions" / "renderer.js"
INTERACTIONS = ROOT / "public" / "js" / "factory_permissions" / "interactions.js"


def _page_surface() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PAGE, CONTROLLER, API, VIEW_MODEL, RENDERER, INTERACTIONS)
    )


def test_role_search_is_inside_one_searchable_dropdown() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    interactions = INTERACTIONS.read_text(encoding="utf-8")
    view_model = VIEW_MODEL.read_text(encoding="utf-8")
    surface = "\n".join((renderer, interactions, view_model))

    assert 'role="combobox"' in renderer
    assert "apc-role-picker" in renderer
    assert "apc-role-menu" in renderer
    assert "apc-role-option" in renderer
    assert "ArrowDown" in interactions
    assert "ArrowUp" in interactions
    assert "roleMenu" in view_model
    assert "ابحث واختر دورًا" in renderer
    assert "apc-role-search" not in surface
    assert "apc-role-select" not in surface


def test_section_and_global_select_all_controls_are_present() -> None:
    renderer = RENDERER.read_text(encoding="utf-8")
    interactions = INTERACTIONS.read_text(encoding="utf-8")
    controller = CONTROLLER.read_text(encoding="utf-8")
    surface = "\n".join((renderer, interactions, controller))

    assert "apc-select-all-group" in renderer
    assert "apc-select-all-global" in renderer
    assert "onGroupToggle" in interactions
    assert "onGlobalToggle" in interactions
    assert "تحديد الكل للكل" in renderer
    assert "إلغاء تحديد الكل للكل" in renderer
    assert "syncBulkControls" in surface


def test_permission_console_never_silently_hides_server_capabilities() -> None:
    source = VIEW_MODEL.read_text(encoding="utf-8")
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
    api_source = API.read_text(encoding="utf-8")
    controller_source = CONTROLLER.read_text(encoding="utf-8")
    renderer_source = RENDERER.read_text(encoding="utf-8")
    interactions_source = INTERACTIONS.read_text(encoding="utf-8")
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

    assert "export_role_permissions" in api_source
    assert "preview_permission_import" in api_source
    assert "JSON.parse(payload)" in controller_source
    assert 'this.value = ""' in interactions_source
    assert "URL.createObjectURL" in renderer_source
    assert "URL.revokeObjectURL" in renderer_source
    assert "لن يتغير الدور قبل الحفظ" in controller_source


def test_bootstrap_loads_the_page_owned_modules() -> None:
    page = PAGE.read_text(encoding="utf-8")
    surface = _page_surface()

    for asset in (
        "api.js",
        "state.js",
        "view_model.js",
        "renderer.js",
        "interactions.js",
        "controller.js",
    ):
        assert f"/assets/almdina_erp/js/factory_permissions/{asset}" in page
    assert "AlmdinaFactoryPermissionsController" in surface
