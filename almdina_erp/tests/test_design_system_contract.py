from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
TOKENS = ROOT / "public" / "css" / "almdina_design_tokens.css"
COMPONENTS = ROOT / "public" / "css" / "almdina_components.css"
DESK_THEME = ROOT / "public" / "css" / "almdina_desk_theme.css"
UI = ROOT / "public" / "js" / "almdina_ui.js"
ASSETS = ROOT / "frontend_assets.py"
PERMISSIONS_RENDERER = ROOT / "public" / "js" / "factory_permissions" / "renderer.js"
PERMISSIONS_CONTROLLER = ROOT / "public" / "js" / "factory_permissions" / "controller.js"
PERMISSIONS_PAGE = ROOT / "almdina_erp" / "page" / "factory_permissions" / "factory_permissions.js"
WORKFORCE_RENDERER = ROOT / "public" / "js" / "factory_workforce" / "renderer.js"
WORKFORCE_CONTROLLER = ROOT / "public" / "js" / "factory_workforce" / "controller.js"
WORKFORCE_PAGE = ROOT / "almdina_erp" / "page" / "factory_workforce" / "factory_workforce.js"
PRODUCTION_SETTINGS_RENDERER = ROOT / "public" / "js" / "factory_production_settings" / "renderer.js"
PRODUCTION_SETTINGS_PAGE = ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js"
SHOP_FLOOR_RENDERER = ROOT / "public" / "js" / "shop_floor_inbox" / "renderer.js"
SHOP_FLOOR_CONTROLLER = ROOT / "public" / "js" / "shop_floor_inbox" / "controller.js"
SHOP_FLOOR_INTERACTIONS = ROOT / "public" / "js" / "shop_floor_inbox" / "interactions.js"
SHOP_FLOOR_PAGE = ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js"
NOTES_PANEL = ROOT / "public" / "js" / "notes" / "notes_panel.js"
DCO_TAB_EDIT = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_page_edit_action_ux.js"
DCO_MEASUREMENT_ACTIONS = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "measurements" / "door_cutting_order_measurement_actions_ux.js"
DCO_BULK_ROWS = ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "measurements" / "door_cutting_order_bulk_rows_ux.js"
DCO_PLAN_UX = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_ux.js"
DCO_DRAWING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_drawing_plan_ux.js"
DCO_PLAN_CONTEXT = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_context_actions_ux.js"
DCO_FINANCIAL_DOCS = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_financial_documents_ux.js"
DCO_INVOICE_TOOLBAR = ROOT / "public" / "js" / "door_cutting_order" / "costing" / "door_cutting_order_customer_invoice_toolbar_ux.js"
DCO_WORKSPACE_ASSET = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_status_ux.js"
DCO_RECOVERY = ROOT / "public" / "js" / "door_cutting_order" / "recovery" / "presentation" / "door_cutting_order_local_checkpoint.js"
SPECIAL_SHAPE_SHELL = ROOT / "public" / "js" / "special_shape_documentation" / "presentation" / "workspace_shell.js"
SPECIAL_SHAPE_PAGE = ROOT / "almdina_erp" / "page" / "door_drawing" / "door_drawing.js"
FACTORY_MASTER_DATA_PAGE = ROOT / "almdina_erp" / "page" / "factory_master_data" / "factory_master_data.js"
FACTORY_PLAN_ARCHIVE_PAGE = ROOT / "almdina_erp" / "page" / "factory_plan_archive" / "factory_plan_archive.js"
DCO_PLAN_TABS = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_plan_tabs_ux.js"
SECURE_DXF_UPLOAD = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "secure_dxf_upload.js"
SHOP_FLOOR_ORDER_UX = ROOT / "public" / "js" / "door_cutting_order" / "production" / "shop_floor_order_ux.js"
FACTORY_PERMISSIONS_CSS = ROOT / "public" / "css" / "factory_permissions.css"
FACTORY_WORKFORCE_CSS = ROOT / "public" / "css" / "factory_workforce.css"
FACTORY_PRODUCTION_SETTINGS_CSS = ROOT / "public" / "css" / "factory_production_settings.css"
FACTORY_ROUTING_WORKFLOW_CSS = ROOT / "public" / "css" / "factory_routing_workflow.css"
FACTORY_STAGE_LIBRARY_CSS = ROOT / "public" / "css" / "factory_stage_library.css"
SHOP_FLOOR_RESPONSIVE_CSS = ROOT / "public" / "css" / "shop_floor_responsive.css"
DCO_RESPONSIVE_CSS = ROOT / "public" / "css" / "door_cutting_order_responsive.css"
DCO_EXTRA_ADDONS_CSS = ROOT / "public" / "css" / "door_cutting_order_extra_addons.css"
SHOP_FLOOR_WORKER_DROPDOWN_CSS = ROOT / "public" / "css" / "shop_floor_worker_dropdown.css"
STATIC_WORKFLOW = ROOT.parent / ".github" / "workflows" / "static-checks.yml"

MIGRATED_SURFACES = (
    PERMISSIONS_RENDERER,
    WORKFORCE_RENDERER,
    PRODUCTION_SETTINGS_RENDERER,
    SHOP_FLOOR_RENDERER,
    NOTES_PANEL,
    DCO_TAB_EDIT,
    DCO_MEASUREMENT_ACTIONS,
    DCO_BULK_ROWS,
    DCO_PLAN_UX,
    DCO_DRAWING_PLAN,
    DCO_PLAN_CONTEXT,
    DCO_FINANCIAL_DOCS,
    DCO_INVOICE_TOOLBAR,
    DCO_WORKSPACE_ASSET,
    DCO_RECOVERY,
    SPECIAL_SHAPE_SHELL,
    FACTORY_MASTER_DATA_PAGE,
    FACTORY_PLAN_ARCHIVE_PAGE,
    DCO_PLAN_TABS,
)
LEGACY_PRESENTATION_ALLOWLIST = frozenset(
    {
        "almdina_ui.js",
        "notes.css",
        "door_cutting_order_mobile_list.css",
    }
)
LEGACY_PRIMARY_MARKERS = (
    'class="btn btn-primary',
    "class='btn btn-primary",
    'class="btn btn-danger',
    "class='btn btn-danger",
)
LEGACY_CSS_PRIMARY_MARKERS = (
    "var(--primary, #2490ef)",
    "var(--primary,#2490ef)",
    "#2490ef",
    "rgba(36, 144, 239",
)
MIGRATED_CSS_SURFACES = (
    FACTORY_PERMISSIONS_CSS,
    FACTORY_WORKFORCE_CSS,
    FACTORY_PRODUCTION_SETTINGS_CSS,
    FACTORY_ROUTING_WORKFLOW_CSS,
    FACTORY_STAGE_LIBRARY_CSS,
    SHOP_FLOOR_RESPONSIVE_CSS,
    SHOP_FLOOR_WORKER_DROPDOWN_CSS,
    DCO_RESPONSIVE_CSS,
    DCO_EXTRA_ADDONS_CSS,
)
WIDGET_MIGRATED_SURFACES = (
    FACTORY_PLAN_ARCHIVE_PAGE,
    WORKFORCE_RENDERER,
    SHOP_FLOOR_RENDERER,
    FACTORY_MASTER_DATA_PAGE,
)
RAW_INPUT_MARKERS = (
    '<input class="apa-search"',
    "<input class='apa-search'",
    '<input id="aw-workforce-search"',
    "<input id='aw-workforce-search'",
    '<input id="almdina-sf-board-search"',
    "<input id='almdina-sf-board-search'",
    '<input class="prw-search"',
    "<input class='prw-search'",
    '<select class="form-control prw-status-filter"',
    "<select class='form-control prw-status-filter'",
    '<input type="search"',
    "<input type='search'",
    '<select id="aw-enabled-filter"',
    "<select id='aw-enabled-filter'",
    '<select id="almdina-sf-route-filter"',
    "<select id='almdina-sf-route-filter'",
    'class="aw-enabled-filter"',
)


def _presentation_asset_paths() -> list[Path]:
    paths: list[Path] = []
    for suffix in (".css", ".js"):
        paths.extend(PUBLIC.rglob(f"*{suffix}"))
    return sorted(
        path
        for path in paths
        if path.name not in LEGACY_PRESENTATION_ALLOWLIST
        and "tests/" not in path.as_posix()
    )


def _contains_legacy_primary(source: str) -> str | None:
    for marker in (*LEGACY_PRIMARY_MARKERS, *LEGACY_CSS_PRIMARY_MARKERS):
        if marker in source:
            return marker
    return None


class TestDesignSystemContract(unittest.TestCase):
    def setUp(self) -> None:
        self.tokens = TOKENS.read_text(encoding="utf-8")
        self.components = COMPONENTS.read_text(encoding="utf-8")
        self.ui = UI.read_text(encoding="utf-8")
        self.assets = ASSETS.read_text(encoding="utf-8")
        self.permissions_renderer = PERMISSIONS_RENDERER.read_text(encoding="utf-8")
        self.permissions_controller = PERMISSIONS_CONTROLLER.read_text(encoding="utf-8")
        self.permissions_page = PERMISSIONS_PAGE.read_text(encoding="utf-8")
        self.workforce_renderer = WORKFORCE_RENDERER.read_text(encoding="utf-8")
        self.workforce_controller = WORKFORCE_CONTROLLER.read_text(encoding="utf-8")
        self.workforce_page = WORKFORCE_PAGE.read_text(encoding="utf-8")
        self.production_settings_renderer = PRODUCTION_SETTINGS_RENDERER.read_text(encoding="utf-8")
        self.production_settings_page = PRODUCTION_SETTINGS_PAGE.read_text(encoding="utf-8")
        self.shop_floor_renderer = SHOP_FLOOR_RENDERER.read_text(encoding="utf-8")
        self.shop_floor_controller = SHOP_FLOOR_CONTROLLER.read_text(encoding="utf-8")
        self.shop_floor_interactions = SHOP_FLOOR_INTERACTIONS.read_text(encoding="utf-8")
        self.shop_floor_page = SHOP_FLOOR_PAGE.read_text(encoding="utf-8")
        self.notes_panel = NOTES_PANEL.read_text(encoding="utf-8")
        self.dco_tab_edit = DCO_TAB_EDIT.read_text(encoding="utf-8")
        self.dco_measurement_actions = DCO_MEASUREMENT_ACTIONS.read_text(encoding="utf-8")
        self.dco_bulk_rows = DCO_BULK_ROWS.read_text(encoding="utf-8")
        self.dco_plan_ux = DCO_PLAN_UX.read_text(encoding="utf-8")
        self.dco_recovery = DCO_RECOVERY.read_text(encoding="utf-8")
        self.special_shape_shell = SPECIAL_SHAPE_SHELL.read_text(encoding="utf-8")
        self.special_shape_page = SPECIAL_SHAPE_PAGE.read_text(encoding="utf-8")
        self.factory_master_data_page = FACTORY_MASTER_DATA_PAGE.read_text(encoding="utf-8")
        self.factory_plan_archive_page = FACTORY_PLAN_ARCHIVE_PAGE.read_text(encoding="utf-8")
        self.dco_plan_tabs = DCO_PLAN_TABS.read_text(encoding="utf-8")

    def test_tokens_define_brand_and_button_primitives(self) -> None:
        self.assertIn(":root,", self.tokens)
        self.assertIn(".almdina-ui", self.tokens)
        self.assertIn("--alm-primary: #172033", self.tokens)
        self.assertIn("--alm-height-button:", self.tokens)
        self.assertIn("--alm-radius-button:", self.tokens)

    def test_components_stay_scoped_and_define_primary_button(self) -> None:
        self.assertIn(".almdina-ui .btn.alm-btn-primary", self.components)
        self.assertIn("background: var(--alm-primary)", self.components)
        self.assertNotIn("body .btn-primary", self.components)

    def test_ui_builder_is_presentation_only(self) -> None:
        self.assertIn("filterGroup", self.ui)
        self.assertIn("frappe.ui.FieldGroup is required for AlmdinaUi.filterGroup", self.ui)
        self.assertIn("function button(", self.ui)
        self.assertIn("function control(", self.ui)
        self.assertIn("function filterGroup(", self.ui)
        self.assertIn("function fileUploader(", self.ui)
        self.assertIn("fileUploaderPresets", self.ui)
        self.assertIn("securePrivate", self.ui)
        self.assertIn("function empty(", self.ui)
        self.assertIn("alm-btn-primary", self.ui)
        self.assertIn("frappe.ui.form.make_control", self.ui)
        self.assertNotIn("frappe.call", self.ui)
        self.assertNotIn("has_permission", self.ui)

    def test_components_define_frappe_control_wrapper(self) -> None:
        self.assertIn(".almdina-ui .alm-control", self.components)
        self.assertIn(".almdina-ui .alm-filter-group", self.components)
        self.assertIn(".almdina-ui .alm-control .form-control:focus", self.components)

    def test_assets_load_design_system_before_feature_css_and_after_foundation(self) -> None:
        tokens_asset = '"/assets/almdina_erp/css/almdina_design_tokens.css"'
        components_asset = '"/assets/almdina_erp/css/almdina_components.css"'
        desk_theme_asset = '"/assets/almdina_erp/css/almdina_desk_theme.css"'
        ui_asset = '"/assets/almdina_erp/js/almdina_ui.js"'
        foundation_asset = '"/assets/almdina_erp/js/frontend_foundation.js"'
        notes_asset = '"/assets/almdina_erp/css/notes.css"'

        self.assertLess(self.assets.index(tokens_asset), self.assets.index(components_asset))
        self.assertLess(self.assets.index(components_asset), self.assets.index(desk_theme_asset))
        self.assertLess(self.assets.index(desk_theme_asset), self.assets.index(notes_asset))
        self.assertLess(self.assets.index(foundation_asset), self.assets.index(ui_asset))

    def test_desk_theme_bridges_frappe_primary_to_alm_tokens(self) -> None:
        source = DESK_THEME.read_text(encoding="utf-8")
        self.assertIn("--primary: var(--alm-primary)", source)
        self.assertIn("--btn-primary: var(--alm-primary)", source)
        self.assertIn(".indicator-pill.blue", source)
        self.assertNotIn("body .btn-primary", source)
        self.assertNotIn("#2490ef", source)

    def test_factory_permissions_pilot_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui apc-shell"', self.permissions_renderer)
        self.assertIn("AlmdinaUi.button", self.permissions_renderer)
        self.assertIn("AlmdinaUi.control is required for Factory Permissions rendering", self.permissions_renderer)
        self.assertIn("mountRoleControl", self.permissions_renderer)
        self.assertIn("apc-role-mount", self.permissions_renderer)
        self.assertIn("roleSearchQuery", self.permissions_controller)
        self.assertNotIn("apc-role-picker", self.permissions_renderer)
        self.assertNotIn('class="btn btn-primary apc-save"', self.permissions_renderer)
        self.assertNotIn('type="file"', self.permissions_renderer)
        self.assertNotIn("apc-import-file", self.permissions_renderer)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.permissions_page)

    def test_factory_workforce_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui aw-shell"', self.workforce_renderer)
        self.assertIn("AlmdinaUi.button", self.workforce_renderer)
        self.assertNotIn('class="btn btn-primary aw-adopt-user"', self.workforce_renderer)
        self.assertNotIn('class="btn btn-danger aw-toggle"', self.workforce_renderer)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.workforce_page)

    def test_factory_production_settings_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui aps-shell"', self.production_settings_renderer)
        self.assertIn("AlmdinaUi.button", self.production_settings_renderer)
        self.assertNotIn('class="btn btn-primary aps-edit"', self.production_settings_renderer)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.production_settings_page)

    def test_shop_floor_inbox_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui almdina-sf-shell"', self.shop_floor_renderer)
        self.assertIn('class="almdina-ui almdina-sf-nav"', self.shop_floor_renderer)
        self.assertIn("AlmdinaUi.button", self.shop_floor_renderer)
        self.assertNotIn('class="btn btn-primary sf-quick-action"', self.shop_floor_renderer)
        self.assertNotIn('class="btn btn-danger almdina-sf-logout"', self.shop_floor_renderer)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.shop_floor_page)

    def test_notes_panel_uses_design_system(self) -> None:
        self.assertIn('class="almdina-notes-panel almdina-ui"', self.notes_panel)
        self.assertIn("AlmdinaUi.button", self.notes_panel)
        self.assertNotIn('class="btn btn-primary almdina-notes-submit"', self.notes_panel)
        self.assertNotIn('class="btn btn-primary btn-xs" data-notes-action="save-edit"', self.notes_panel)

    def test_dco_hotspots_use_design_system(self) -> None:
        self.assertIn("AlmdinaUi.button", self.dco_tab_edit)
        self.assertIn("almdina-ui", self.dco_tab_edit)
        self.assertNotIn('class="btn btn-sm btn-primary dco-tab-edit-save"', self.dco_tab_edit)

        self.assertIn("AlmdinaUi.button", self.dco_measurement_actions)
        self.assertIn("dco-entry-window-actions almdina-ui", self.dco_measurement_actions)
        self.assertNotIn('class="btn btn-primary dco-inline-order-edit-save"', self.dco_measurement_actions)

        self.assertIn("AlmdinaUi.button", self.dco_bulk_rows)
        self.assertIn("dco-bulk-footer almdina-ui", self.dco_bulk_rows)
        self.assertNotIn('class="btn btn-primary btn-sm dco-add-row"', self.dco_bulk_rows)

        self.assertIn("AlmdinaUi.button", self.dco_plan_ux)
        self.assertIn("almdina-ui dco-plan-actions-shell", self.dco_plan_ux)
        self.assertNotIn('class="btn btn-primary btn-sm dco-recalculate-plan"', self.dco_plan_ux)

        self.assertIn("AlmdinaUi.button", self.dco_recovery)
        self.assertIn("dco-recovery-card__actions almdina-ui", self.dco_recovery)
        self.assertNotIn('class="btn btn-primary btn-sm" data-recovery-action="continue"', self.dco_recovery)

    def test_special_shape_documentation_uses_design_system(self) -> None:
        self.assertIn('class="ald-doc-workspace almdina-ui"', self.special_shape_shell)
        self.assertIn("AlmdinaUi.button", self.special_shape_shell)
        self.assertNotIn('class="ald-doc-primary"', self.special_shape_shell)
        self.assertNotIn('class="ald-doc-danger"', self.special_shape_shell)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.special_shape_page)

    def test_factory_master_data_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui prw-shell"', self.factory_master_data_page)
        self.assertIn("uiButton(", self.factory_master_data_page)
        self.assertIn("AlmdinaUi.control is required for factory master data rendering", self.factory_master_data_page)
        self.assertIn("AlmdinaUi.filterGroup is required for factory master data rendering", self.factory_master_data_page)
        self.assertIn("mountToolbarControls", self.factory_master_data_page)
        self.assertIn("prw-filter-group-mount", self.factory_master_data_page)
        self.assertIn("toolbarFilterFields", self.factory_master_data_page)
        self.assertIn("mountStageControls", self.factory_master_data_page)
        self.assertNotIn("prw-search-mount", self.factory_master_data_page)
        self.assertNotIn("prw-status-mount", self.factory_master_data_page)
        self.assertIn("prw-stage-role-mount", self.factory_master_data_page)
        self.assertIn("search_operational_roles", self.factory_master_data_page)
        self.assertNotIn('data-stage-field="operational_role"', self.factory_master_data_page)
        self.assertIn('page.set_primary_action(__("مسار إنتاج جديد")', self.factory_master_data_page)
        self.assertIn("syncPrimaryAction()", self.factory_master_data_page)
        self.assertNotIn("prw-new-route", self.factory_master_data_page)
        self.assertNotIn('class="btn btn-primary prw-save-route"', self.factory_master_data_page)
        self.assertNotIn('class="btn btn-danger prw-delete-route"', self.factory_master_data_page)
        self.assertNotIn('class="prw-search"', self.factory_master_data_page)
        self.assertNotIn("prw-status-filter", self.factory_master_data_page)

    def test_factory_plan_archive_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui apa-shell"', self.factory_plan_archive_page)
        self.assertIn("AlmdinaUi.button", self.factory_plan_archive_page)
        self.assertIn("AlmdinaUi.control", self.factory_plan_archive_page)
        self.assertIn("disposeControls", self.factory_plan_archive_page)
        self.assertNotIn('class="btn btn-primary apa-archive"', self.factory_plan_archive_page)

    def test_widget_migrated_surfaces_reject_raw_search_inputs(self) -> None:
        for path in WIDGET_MIGRATED_SURFACES:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                for marker in RAW_INPUT_MARKERS:
                    self.assertNotIn(marker, source, msg=f"{path.name} still contains {marker}")

    def test_migrated_admin_pages_use_frappe_page_toolbar_actions(self) -> None:
        self.assertNotIn("aw-refresh", self.workforce_renderer)
        self.assertIn('add_inner_button(__("تحديث"), load, null, "refresh")', self.workforce_controller)
        self.assertIn('set_primary_action(__("إنشاء مستخدم جديد"), openCreateDialog, "add")', self.workforce_controller)

        self.assertNotIn("almdina-sf-refresh", self.shop_floor_renderer)
        self.assertNotIn("almdina-sf-refresh", self.shop_floor_interactions)
        self.assertIn('add_inner_button(__("تحديث"), refresh, null, "refresh")', self.shop_floor_controller)
        self.assertIn("syncRefreshButtonVisibility", self.shop_floor_controller)

        self.assertIn('page.set_primary_action(__("مسار إنتاج جديد")', self.factory_master_data_page)
        self.assertIn("syncPrimaryAction()", self.factory_master_data_page)
        self.assertIn('this.page.add_inner_button(', self.factory_master_data_page)
        self.assertIn('page.set_primary_action(__("تحديث"), load, "refresh")', self.factory_plan_archive_page)

    def test_migrated_admin_dialogs_reject_structured_prompts(self) -> None:
        shop_floor_dialogs = (ROOT / "public" / "js" / "shop_floor_inbox" / "dialogs.js").read_text(encoding="utf-8")
        permissions_dialogs = (ROOT / "public" / "js" / "factory_permissions" / "dialogs.js").read_text(encoding="utf-8")
        self.assertNotIn("frappe.prompt", shop_floor_dialogs)
        self.assertIn("createWorkerDropdownDialog", shop_floor_dialogs)
        self.assertIn('fieldtype: "Attach"', permissions_dialogs)
        self.assertIn("permissions_file", permissions_dialogs)
        self.assertNotIn("frappe.prompt", permissions_dialogs)

    def test_dco_plan_tabs_use_design_system_tokens(self) -> None:
        self.assertIn('class="almdina-ui dco-plan-tabs"', self.dco_plan_tabs)
        self.assertIn('"is-active"', self.dco_plan_tabs)
        self.assertNotIn('"btn-primary"', self.dco_plan_tabs)
        self.assertIn(".almdina-ui .dco-plan-tabs .btn.is-active", self.components)

    def test_migrated_surfaces_reject_legacy_primary_markup(self) -> None:
        for path in MIGRATED_SURFACES:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                for marker in LEGACY_PRIMARY_MARKERS:
                    self.assertNotIn(marker, source, msg=f"{path.name} still contains {marker}")

    def test_migrated_css_surfaces_use_alm_primary_tokens(self) -> None:
        for path in MIGRATED_CSS_SURFACES:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("--alm-primary", source, msg=f"{path.name} should read design tokens")
                for marker in LEGACY_CSS_PRIMARY_MARKERS:
                    self.assertNotIn(marker, source, msg=f"{path.name} still contains {marker}")

    def test_factory_routing_workflow_aliases_brand_primary(self) -> None:
        source = FACTORY_ROUTING_WORKFLOW_CSS.read_text(encoding="utf-8")
        self.assertIn("--prw-primary: var(--alm-primary, #172033)", source)

    def test_shop_floor_responsive_aliases_brand_primary(self) -> None:
        source = SHOP_FLOOR_RESPONSIVE_CSS.read_text(encoding="utf-8")
        self.assertIn("--sf-primary: var(--alm-primary, #172033)", source)

    def test_public_presentation_assets_reject_legacy_frappe_primary(self) -> None:
        for path in _presentation_asset_paths():
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                marker = _contains_legacy_primary(path.read_text(encoding="utf-8"))
                self.assertIsNone(marker, msg=f"{path.name} still contains {marker}")

    def test_migrated_js_surfaces_using_builder_are_registered(self) -> None:
        registered = {path.resolve() for path in MIGRATED_SURFACES}
        builder_surfaces = sorted(
            path.resolve()
            for path in PUBLIC.rglob("*.js")
            if "AlmdinaUi.button" in path.read_text(encoding="utf-8")
        )
        missing = [path for path in builder_surfaces if path not in registered]
        self.assertFalse(
            missing,
            msg="Add migrated AlmdinaUi.button surfaces to MIGRATED_SURFACES: "
            + ", ".join(path.name for path in missing),
        )

    def test_legacy_presentation_allowlist_stays_intentional(self) -> None:
        self.assertIn("notes.css", LEGACY_PRESENTATION_ALLOWLIST)
        self.assertIn("door_cutting_order_mobile_list.css", LEGACY_PRESENTATION_ALLOWLIST)

    def test_design_system_tests_are_static_gates(self) -> None:
        workflow = STATIC_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("almdina_erp.tests.test_design_system_contract", workflow)
        self.assertIn("node almdina_erp/tests/js/almdina_ui.test.js", workflow)

    def test_secure_dxf_upload_uses_almdina_file_uploader_preset(self) -> None:
        source = SECURE_DXF_UPLOAD.read_text(encoding="utf-8")
        self.assertIn("AlmdinaUi.fileUploader", source)
        self.assertIn('preset: "securePrivate"', source)
        self.assertNotIn("new frappe.ui.FileUploader", source)
        self.assertIn("__uploadProductionDxfCore", source)

    def test_shop_floor_dxf_entry_delegates_to_secure_core(self) -> None:
        source = SHOP_FLOOR_ORDER_UX.read_text(encoding="utf-8")
        self.assertIn("__uploadProductionDxfCore", source)
        self.assertIn("frappe.almdina.upload_production_dxf = uploadDrawingDxf", source)
        self.assertNotIn("new frappe.ui.FileUploader", source)
        self.assertIn('preset: "securePrivate"', source)


if __name__ == "__main__":
    unittest.main()
