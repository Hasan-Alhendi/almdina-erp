from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
TOKENS = ROOT / "public" / "css" / "almdina_design_tokens.css"
COMPONENTS = ROOT / "public" / "css" / "almdina_components.css"
PATTERNS = ROOT / "public" / "css" / "almdina_patterns.css"
PAGE_TEMPLATES = ROOT / "public" / "css" / "almdina_page_templates.css"
DESK_THEME = ROOT / "public" / "css" / "almdina_desk_theme.css"
WORKSPACE_HOME_CSS = ROOT / "public" / "css" / "almdina_workspace_home.css"
UI = ROOT / "public" / "js" / "almdina_ui.js"
ASSETS = ROOT / "frontend_assets.py"
TOKEN_OWNERSHIP = ROOT.parent / "docs" / "design_system" / "TOKEN_OWNERSHIP.md"
EDGE_BANDING_UX = ROOT / "public" / "js" / "edge_banding_type_ux.js"
SHARED_DS_CSS = (
    TOKENS,
    COMPONENTS,
    PATTERNS,
    PAGE_TEMPLATES,
    DESK_THEME,
    ROOT / "public" / "css" / "almdina_list_table.css",
)
FEATURE_SELECTOR_PREFIXES = (
    "apc-",
    "aps-",
    "aw-",
    "prw-",
    "sf-",
    "dco-",
    "apa-",
    "almdina-sf-",
)
# Temporary shared-layer leakage until Patterns/Tabs migration.
SHARED_FEATURE_SELECTOR_ALLOWLIST = frozenset(
    {
        ".dco-plan-tabs",
        ".dco-tab-edit-toolbar",
    }
)
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


def _asset_identity(path: str) -> str:
    return path.split("?", 1)[0]


def _string_list_assignment(source: str, name: str) -> list[str]:
    module = ast.parse(source)
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        if node.targets[0].id != name or not isinstance(node.value, ast.List):
            continue
        values: list[str] = []
        for element in node.value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                raise AssertionError(f"{name} must contain only string literals")
            values.append(element.value)
        return values
    raise AssertionError(f"Could not find string list assignment for {name}")


def _feature_selectors(source: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(r"\.([A-Za-z][A-Za-z0-9_-]*)", source):
        class_name = match.group(1)
        if any(class_name.startswith(prefix) for prefix in FEATURE_SELECTOR_PREFIXES):
            found.add(f".{class_name}")
    return found


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

    def test_tokens_define_foundation_scales(self) -> None:
        for token in (
            "--alm-font-size-xs:",
            "--alm-font-size-sm:",
            "--alm-font-size-md:",
            "--alm-font-size-lg:",
            "--alm-font-size-xl:",
            "--alm-font-size-2xl:",
            "--alm-line-height-normal:",
            "--alm-font-weight-bold:",
            "--alm-space-1:",
            "--alm-space-2:",
            "--alm-space-3:",
            "--alm-space-4:",
            "--alm-space-6:",
            "--alm-space-8:",
            "--alm-radius-xs:",
            "--alm-radius-sm:",
            "--alm-radius-md:",
            "--alm-radius-card:",
            "--alm-radius-lg:",
            "--alm-radius-pill:",
            "--alm-shadow-sm:",
            "--alm-shadow-card:",
            "--alm-shadow-md:",
            "--alm-shadow-overlay:",
            "--alm-shadow-focus:",
            "--alm-status-success-fg:",
            "--alm-status-success-bg:",
            "--alm-status-warning-fg:",
            "--alm-status-danger-fg:",
            "--alm-status-info-fg:",
            "--alm-status-neutral-fg:",
        ):
            self.assertIn(token, self.tokens, msg=f"missing foundation token {token}")

    def test_token_ownership_contract_is_documented(self) -> None:
        self.assertTrue(TOKEN_OWNERSHIP.is_file(), msg="TOKEN_OWNERSHIP.md must exist")
        ownership = TOKEN_OWNERSHIP.read_text(encoding="utf-8")
        self.assertIn("`alm-*`", ownership)
        self.assertIn("visual identity only", ownership.lower())
        self.assertIn("Feature CSS", ownership)
        self.assertIn("test_design_system_contract", ownership)

    def test_shared_design_system_css_rejects_new_feature_selectors(self) -> None:
        for path in SHARED_DS_CSS:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                leaked = _feature_selectors(source) - SHARED_FEATURE_SELECTOR_ALLOWLIST
                self.assertFalse(
                    leaked,
                    msg=(
                        f"{path.name} contains Feature selectors outside allowlist: "
                        + ", ".join(sorted(leaked))
                    ),
                )

    def test_frontend_asset_paths_are_unique(self) -> None:
        for list_name in ("app_include_css", "app_include_js"):
            with self.subTest(list_name=list_name):
                values = _string_list_assignment(self.assets, list_name)
                identities = [_asset_identity(value) for value in values]
                duplicates = sorted(
                    {
                        identity
                        for identity in identities
                        if identities.count(identity) > 1
                    }
                )
                self.assertFalse(
                    duplicates,
                    msg=f"{list_name} has duplicate asset paths: " + ", ".join(duplicates),
                )

    def test_components_stay_scoped_and_define_primary_button(self) -> None:
        self.assertIn(".almdina-ui .btn.alm-btn-primary", self.components)
        self.assertIn(".almdina-ui .btn.alm-btn-secondary", self.components)
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
        self.assertIn("function badge(", self.ui)
        self.assertIn("function status(", self.ui)
        self.assertIn("function state(", self.ui)
        self.assertIn("alm-btn-primary", self.ui)
        self.assertIn("alm-btn-secondary", self.ui)
        self.assertIn("alm-badge--", self.ui)
        self.assertIn("alm-status--", self.ui)
        self.assertIn("alm-state--", self.ui)
        self.assertIn("frappe.ui.form.make_control", self.ui)
        self.assertIn("df.change = function nativeChangeBridge", self.ui)
        self.assertNotIn("input.on(\"input change\"", self.ui)
        self.assertNotIn("frappeControl.change =", self.ui)
        self.assertNotRegex(self.ui, r"\.off\(\s*[\"'](?:input|change|input change)")
        self.assertNotIn("field.change = function patchedChange", self.ui)
        self.assertNotIn("frappe.call", self.ui)
        self.assertNotIn("has_permission", self.ui)

    def test_components_define_shared_composition_primitives(self) -> None:
        for marker in (
            ".almdina-ui .alm-card",
            ".almdina-ui .alm-card--muted",
            ".almdina-ui .alm-panel",
            ".almdina-ui .alm-panel__header",
            ".almdina-ui .alm-panel__body",
            ".almdina-ui .alm-badge",
            ".almdina-ui .alm-badge--success",
            ".almdina-ui .alm-status",
            ".almdina-ui .alm-status--danger",
            ".almdina-ui .alm-state",
            ".almdina-ui .alm-state--loading",
            ".almdina-ui .alm-state--empty",
            ".almdina-ui .alm-state--error",
            ".almdina-ui .alm-state__spinner",
        ):
            self.assertIn(marker, self.components, msg=f"missing component selector {marker}")

    def test_admin_pages_use_shared_bootstrap_state(self) -> None:
        for path in (
            PERMISSIONS_PAGE,
            PRODUCTION_SETTINGS_PAGE,
            WORKFORCE_PAGE,
            SHOP_FLOOR_PAGE,
            FACTORY_MASTER_DATA_PAGE,
        ):
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertTrue(
                    "ui.state({" in source or "ui.state({ kind" in source or "paintState(" in source,
                    msg=f"{path.name} must use AlmdinaUi.state bootstrap shell",
                )
                self.assertTrue(
                    'kind: "error"' in source
                    or 'paintState("error"' in source
                    or "alm-state--error" in source,
                    msg=f"{path.name} must render shared error state",
                )
                self.assertNotIn(
                    'style="padding:24px;text-align:center"',
                    source,
                    msg=f"{path.name} still uses inline bootstrap error card",
                )

    def test_components_define_frappe_control_wrapper(self) -> None:
        self.assertIn(".almdina-ui .alm-control", self.components)
        self.assertIn(".almdina-ui .alm-filter-group", self.components)
        self.assertIn(".almdina-ui .alm-control .form-control:focus", self.components)

    def test_assets_load_design_system_before_feature_css_and_after_foundation(self) -> None:
        tokens_asset = '"/assets/almdina_erp/css/almdina_design_tokens.css"'
        components_asset = '"/assets/almdina_erp/css/almdina_components.css"'
        patterns_asset = '"/assets/almdina_erp/css/almdina_patterns.css"'
        templates_asset = '"/assets/almdina_erp/css/almdina_page_templates.css"'
        desk_theme_asset = '"/assets/almdina_erp/css/almdina_desk_theme.css"'
        desk_sidebar_asset = '"/assets/almdina_erp/css/almdina_desk_sidebar.css?v=2"'
        workspace_home_asset = '"/assets/almdina_erp/css/almdina_workspace_home.css?v=10"'
        ui_asset = '"/assets/almdina_erp/js/almdina_ui.js"'
        foundation_asset = '"/assets/almdina_erp/js/frontend_foundation.js"'
        notes_asset = '"/assets/almdina_erp/css/notes.css"'

        self.assertLess(self.assets.index(tokens_asset), self.assets.index(components_asset))
        self.assertLess(self.assets.index(components_asset), self.assets.index(patterns_asset))
        self.assertLess(self.assets.index(patterns_asset), self.assets.index(templates_asset))
        self.assertLess(self.assets.index(templates_asset), self.assets.index(desk_theme_asset))
        self.assertLess(self.assets.index(desk_theme_asset), self.assets.index(desk_sidebar_asset))
        self.assertLess(self.assets.index(desk_sidebar_asset), self.assets.index(workspace_home_asset))
        self.assertLess(self.assets.index(workspace_home_asset), self.assets.index(notes_asset))
        self.assertLess(self.assets.index(foundation_asset), self.assets.index(ui_asset))

    def test_patterns_define_shared_admin_composition(self) -> None:
        patterns = PATTERNS.read_text(encoding="utf-8")
        for marker in (
            ".almdina-ui .alm-page-intro",
            ".almdina-ui .alm-page-intro--accented",
            ".almdina-ui .alm-page-intro__eyebrow",
            ".almdina-ui .alm-section-header",
            ".almdina-ui .alm-toolbar",
            ".almdina-ui .alm-summary-grid",
            ".almdina-ui .alm-summary-card",
            '.almdina-ui .alm-summary-card[data-tone="success"]',
        ):
            self.assertIn(marker, patterns, msg=f"missing pattern selector {marker}")

    def test_admin_console_surfaces_adopt_shared_patterns(self) -> None:
        permissions = PERMISSIONS_RENDERER.read_text(encoding="utf-8")
        workforce = WORKFORCE_RENDERER.read_text(encoding="utf-8")
        settings = PRODUCTION_SETTINGS_RENDERER.read_text(encoding="utf-8")

        self.assertIn("apc-hero alm-page-intro", permissions)
        self.assertIn("alm-summary-grid", permissions)
        self.assertIn('data-tone="success"', permissions)

        self.assertIn("aw-hero alm-page-intro alm-page-intro--accented", workforce)
        self.assertIn("aw-toolbar alm-toolbar", workforce)
        self.assertIn("aw-summary alm-summary-grid", workforce)

        self.assertIn("aps-hero alm-page-intro alm-page-intro--accented", settings)
        self.assertIn("aps-section-intro alm-section-header", settings)

    def test_page_templates_define_family_grammar(self) -> None:
        templates = PAGE_TEMPLATES.read_text(encoding="utf-8")
        for marker in (
            ".almdina-ui.alm-page",
            ".almdina-ui.alm-page--admin",
            ".almdina-ui.alm-page--workbench",
            ".almdina-ui.alm-page--list",
            ".almdina-ui.alm-page--transaction",
            "body:has(.frappe-list)",
            "--alm-page-max-width",
        ):
            self.assertIn(marker, templates, msg=f"missing page template marker {marker}")

    def test_surfaces_adopt_page_template_families(self) -> None:
        permissions = PERMISSIONS_RENDERER.read_text(encoding="utf-8")
        workforce = WORKFORCE_RENDERER.read_text(encoding="utf-8")
        settings = PRODUCTION_SETTINGS_RENDERER.read_text(encoding="utf-8")
        master_data = FACTORY_MASTER_DATA_PAGE.read_text(encoding="utf-8")
        shop_floor = SHOP_FLOOR_RENDERER.read_text(encoding="utf-8")
        plan_archive = FACTORY_PLAN_ARCHIVE_PAGE.read_text(encoding="utf-8")
        edge_banding = EDGE_BANDING_UX.read_text(encoding="utf-8")

        self.assertIn("apc-shell alm-page alm-page--admin", permissions)
        self.assertIn("aw-shell alm-page alm-page--admin", workforce)
        self.assertIn("aps-shell alm-page alm-page--admin", settings)
        self.assertIn("apa-shell alm-page alm-page--admin", plan_archive)

        self.assertIn("prw-shell alm-page alm-page--workbench", master_data)
        self.assertIn("almdina-sf-shell alm-page alm-page--workbench", shop_floor)

        self.assertIn("ebt-form-page almdina-ui alm-page alm-page--transaction", edge_banding)

    def test_desk_theme_bridges_frappe_primary_to_alm_tokens(self) -> None:
        source = DESK_THEME.read_text(encoding="utf-8")
        self.assertIn("--primary: var(--alm-primary)", source)
        self.assertIn("--btn-primary: var(--alm-primary)", source)
        self.assertIn(".indicator-pill.blue", source)
        self.assertNotIn("body .btn-primary", source)
        self.assertNotIn("#2490ef", source)

    def test_workspace_home_css_uses_design_tokens_without_global_desk_overrides(self) -> None:
        source = WORKSPACE_HOME_CSS.read_text(encoding="utf-8")
        tokens = TOKENS.read_text(encoding="utf-8")
        self.assertIn("--alm-home-surface", source)
        self.assertIn("var(--alm-canvas)", source)
        self.assertIn("body.almdina-workspace-home", source)
        self.assertNotIn("body .btn-primary", source)
        self.assertNotIn("#2490ef", source)
        self.assertIn("--alm-accent-blue", tokens)
        self.assertIn("--alm-accent-purple", tokens)
        self.assertIn("var(--alm-accent-blue)", source)
        self.assertIn("var(--alm-accent-purple)", source)
        self.assertNotIn("#7c3aed", source)

    def test_factory_permissions_pilot_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui apc-shell alm-page alm-page--admin"', self.permissions_renderer)
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
        self.assertIn('class="almdina-ui aw-shell alm-page alm-page--admin"', self.workforce_renderer)
        self.assertIn("AlmdinaUi.button", self.workforce_renderer)
        self.assertNotIn('class="btn btn-primary aw-adopt-user"', self.workforce_renderer)
        self.assertNotIn('class="btn btn-danger aw-toggle"', self.workforce_renderer)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.workforce_page)

    def test_factory_production_settings_uses_design_system(self) -> None:
        self.assertIn('class="almdina-ui aps-shell alm-page alm-page--admin"', self.production_settings_renderer)
        self.assertIn("AlmdinaUi.button", self.production_settings_renderer)
        self.assertNotIn('class="btn btn-primary aps-edit"', self.production_settings_renderer)
        self.assertIn("/assets/almdina_erp/js/almdina_ui.js", self.production_settings_page)

    def test_shop_floor_inbox_uses_design_system(self) -> None:
        self.assertIn("almdina-ui almdina-sf-shell alm-page alm-page--workbench", self.shop_floor_renderer)
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
        self.assertIn("almdina-ui prw-shell alm-page alm-page--workbench", self.factory_master_data_page)
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
        self.assertIn('class="almdina-ui apa-shell alm-page alm-page--admin"', self.factory_plan_archive_page)
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
        self.assertIn("almdina-ui dco-plan-tabs", self.dco_plan_tabs)
        self.assertIn("dco-plan-tabs--underline", self.dco_plan_tabs)
        self.assertIn("aria-selected", self.dco_plan_tabs)
        self.assertIn("is-active", self.dco_plan_tabs)
        self.assertNotIn('"btn-primary"', self.dco_plan_tabs)
        self.assertIn(".almdina-ui .dco-plan-tabs .btn.is-active", self.components)
        self.assertIn("var(--alm-primary)", self.components)

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

    def test_admin_console_shells_alias_foundation_tokens(self) -> None:
        permissions = FACTORY_PERMISSIONS_CSS.read_text(encoding="utf-8")
        workforce = FACTORY_WORKFORCE_CSS.read_text(encoding="utf-8")
        settings = FACTORY_PRODUCTION_SETTINGS_CSS.read_text(encoding="utf-8")

        self.assertIn("--apc-primary: var(--alm-primary, #172033)", permissions)
        self.assertIn("--apc-radius-md: var(--alm-radius-md, 14px)", permissions)
        self.assertIn("--apc-success-soft: var(--alm-status-success-bg)", permissions)

        self.assertIn("--aw-radius-lg: var(--alm-radius-lg, 18px)", workforce)
        self.assertIn("--aw-shadow-md: var(--alm-shadow-md)", workforce)
        self.assertIn("--aw-danger-soft: var(--alm-status-danger-bg)", workforce)

        self.assertIn("--aps-radius-sm: var(--alm-radius-sm, 10px)", settings)
        self.assertIn("--aps-shadow-sm: var(--alm-shadow-sm)", settings)
        self.assertIn("--aps-info-soft: var(--alm-status-info-bg)", settings)

    def test_admin_console_badges_use_shared_status_tones(self) -> None:
        permissions_js = self.permissions_renderer
        workforce_js = self.workforce_renderer
        settings_js = self.production_settings_renderer
        permissions_css = FACTORY_PERMISSIONS_CSS.read_text(encoding="utf-8")
        workforce_css = FACTORY_WORKFORCE_CSS.read_text(encoding="utf-8")
        settings_css = FACTORY_PRODUCTION_SETTINGS_CSS.read_text(encoding="utf-8")

        self.assertIn("AlmdinaUi.badge", permissions_js)
        self.assertIn("AlmdinaUi.badge", workforce_js)
        self.assertIn("AlmdinaUi.badge", settings_js)
        self.assertIn('className: `apc-badge ${badge.kind}`', permissions_js)
        self.assertIn('className: "aw-badge aw-role"', workforce_js)
        self.assertIn("aps-status-pill", settings_js)

        # Feature CSS may size badges; it must not own status palettes.
        self.assertNotIn(".apc-badge.critical", permissions_css)
        self.assertNotIn(".apc-badge.sensitive", permissions_css)
        self.assertNotIn(".aw-badge.is-enabled", workforce_css)
        self.assertNotIn(".aw-badge.is-disabled", workforce_css)
        self.assertNotIn(".aps-status-pill.is-allowed", settings_css)
        self.assertNotIn(".aps-status-pill.is-denied", settings_css)
        self.assertIn(".apc-badge.alm-badge", permissions_css)
        self.assertIn(".aw-badge.alm-badge", workforce_css)
        self.assertIn(".aps-status-pill.alm-badge", settings_css)

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
