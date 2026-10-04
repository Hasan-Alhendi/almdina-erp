from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
OWNER = PUBLIC / "core" / "door_cutting_order_form_presentation_owner.js"
CONTEXT = PUBLIC / "core" / "door_cutting_order_document_context.js"
SIDEBAR = PUBLIC / "core" / "door_cutting_order_form_sidebar_controller.js"
HEADER = PUBLIC / "responsive" / "door_cutting_order_header_ux.js"
TOOLBAR = PUBLIC / "core" / "door_cutting_order_toolbar_stability_ux.js"
OPERATOR = PUBLIC / "order_entry" / "door_cutting_order_operator_ux.js"
ASSETS = ROOT / "frontend_assets.py"
PRESENTATION_CSS = ROOT / "public" / "css" / "door_cutting_order_form_presentation.css"
PAGE_EDIT_ACTION = PUBLIC / "core" / "door_cutting_order_page_edit_action_ux.js"
STATIC_WORKFLOW = ROOT.parent / ".github" / "workflows" / "static-checks.yml"
DCO_WORKFLOW = ROOT.parent / ".github" / "workflows" / "f6-dco-frontend.yml"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def split_selectors(value: str) -> list[str]:
    result = []
    start = 0
    depth = 0
    for index, character in enumerate(value):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == "," and depth == 0:
            result.append(value[start:index].strip())
            start = index + 1
    result.append(value[start:].strip())
    return result


def test_form_presentation_has_one_lifecycle_owner_and_current_dom_probe():
    owner = text(OWNER)
    context = text(CONTEXT)
    assets = text(ASSETS)

    assert 'const SURFACE_NAME = "dco-form-presentation"' in owner
    assert 'context.registerSurface(SURFACE_NAME' in owner
    assert "isReady," in owner and "recover," in owner
    assert '&& element.isConnected' in owner
    assert 'frm._dco_fixed_tabs === current.tabs' in owner
    assert 'frm._dco_tabs_placeholder === current.placeholder' in owner
    assert 'frm._dco_presentation_head === current.head' in owner
    assert 'frm._dco_presentation_root === current.root' in owner
    assert 'frm._dco_presentation_head = null' in context
    assert 'frm._dco_presentation_root = null' in context
    assert 'frm._dco_presentation_page_container = null' in context
    assert "recover(frm)" in owner
    assert "frm.reload_doc(" not in owner
    assert "frm.refresh(" not in owner
    assert '"dco-form-presentation"' in owner
    assert "registerSurface," in context
    assert assets.index('door_cutting_order_document_context.js') < assets.index(
        'door_cutting_order_form_sidebar_controller.js'
    ) < assets.index('door_cutting_order_form_presentation_owner.js')


def test_shell_ownership_is_separate_from_operator_and_action_permissions():
    owner = text(OWNER)
    operator = text(OPERATOR)
    header = text(HEADER)
    toolbar = text(TOOLBAR)

    assert 'current.root.classList.add(ROOT_CLASS)' in owner
    assert 'current.head.classList.add("dco-responsive-head", "dco-stable-actions-head")' in owner
    assert 'current.tabs.classList.add("dco-sticky-tabs")' in owner
    assert 'before_load(frm) { primeShell(frm); }' in owner
    assert '$(frm.wrapper).addClass("dco-operator-form")' not in operator
    assert 'head.classList.add("dco-responsive-head")' not in header
    assert 'tabs.classList.add("dco-sticky-tabs")' not in header
    assert 'head.classList.add("dco-stable-actions-head")' not in toolbar
    assert "frm.doc.status" not in owner
    assert "Administrator" not in owner and "Designer" not in owner
    assert "frappe.user_roles" not in owner


def test_frappe_dom_replacement_and_sidebar_preference_are_reconciled_idempotently():
    owner = text(OWNER)
    sidebar = text(SIDEBAR)
    header = text(HEADER)
    toolbar = text(TOOLBAR)

    assert 'frm.page && frm.page.wrapper' in owner
    assert 'tabs.previousElementSibling' in owner
    assert 'placeholders.forEach' in owner
    assert 'sidebar.mount(frm)' in owner
    assert 'isPreferenceApplied' in sidebar
    assert 'this.preferredExpanded = preferenceStore.read()' in sidebar
    assert 'setup_sidebar_toggle(wrapper)' in sidebar
    assert 'if (isMobile()) return;' in sidebar
    assert 'this.boundRoot === root && root.isConnected' in sidebar
    assert 'previous.off(`hide${EVENT_NAMESPACE}`, this.handleFormHide)' in sidebar
    assert 'updateFixedTabs(frm)' in header
    assert 'const tabs = frm && frm._dco_fixed_tabs' in header
    assert 'document.removeEventListener("scroll", schedule, true)' in header
    assert 'window.removeEventListener("resize", schedule)' in header
    assert 'suspendPresentation(frm)' in header and 'clearFixedTabListeners' in header
    assert 'frm._dco_presentation_head' in toolbar
    assert 'function pageHead(frm)' not in toolbar
    assert 'frm._dcoToolbarObservedHead === head && frm._dcoToolbarObserver' in toolbar
    assert 'frm._dcoToolbarObserver.disconnect()' in toolbar
    assert 'frm._dcoMeasurementToolbarObserver.disconnect()' in toolbar
    assert 'suspendPresentation(frm)' in toolbar
    assert 'dedupeButtons(head)' in toolbar
    assert '[0, 180]' not in toolbar
    assert 'root.querySelector(TOGGLE_SELECTOR)' in sidebar


def test_static_styles_load_with_manifest_and_are_not_injected_at_refresh():
    assets = text(ASSETS)
    css = text(PRESENTATION_CSS)
    header = text(HEADER)
    toolbar = text(TOOLBAR)

    assert assets.count('"/assets/almdina_erp/css/door_cutting_order_form_sidebar.css"') == 1
    assert assets.count('"/assets/almdina_erp/css/door_cutting_order_form_presentation.css"') == 1
    assert '"/assets/almdina_erp/css/door_cutting_order_form_presentation.css"' in assets
    assert ".dco-sticky-tabs .nav-link.active" in css
    assert ".page-head.dco-stable-actions-head .page-actions" in css
    assert ".page-head.dco-responsive-head .page-actions" in css
    assert "position:fixed!important" in css
    assert "border-radius" in css
    assert "style.textContent" not in header and "style.textContent" not in toolbar
    assert "node almdina_erp/tests/js/dco_form_presentation_owner.test.js" in text(STATIC_WORKFLOW)
    assert "node almdina_erp/tests/js/dco_form_presentation_owner.test.js" in text(DCO_WORKFLOW)


def test_every_presentation_css_selector_is_scoped_to_a_live_dco_shell():
    css = text(PRESENTATION_CSS)
    selectors = []
    for match in re.finditer(r"([^{}]+)\{", css):
        prelude = match.group(1).strip()
        if prelude.startswith("@"):
            continue
        selectors.extend(split_selectors(prelude))

    assert selectors
    for selector in selectors:
        assert ".dco-operator-form" in selector or ".dco-form-presentation-shell" in selector, selector
        if any(token in selector for token in (".page-head", ".form-tabs", ".page-actions", ".layout-side-section", ".btn")):
            assert ".dco-operator-form" in selector or ".dco-form-presentation-shell" in selector, selector


def test_native_tab_row_keeps_inner_flex_contract_and_outer_sticky_geometry():
    css = text(PRESENTATION_CSS)
    page_edit = text(PAGE_EDIT_ACTION)
    rules = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        prelude, declarations = match.groups()
        prelude = prelude.strip()
        if prelude.startswith("@"):
            continue
        rules.append((set(split_selectors(prelude)), re.sub(r"\s+", "", declarations)))

    inner_row_selectors = {
        ".dco-operator-form .dco-sticky-tabs .form-tabs-list",
        ".dco-operator-form .dco-sticky-tabs .nav-tabs",
        ".dco-operator-form .dco-sticky-tabs > .form-tabs",
        ".dco-operator-form .form-tabs-list.dco-sticky-tabs > .form-tabs",
    }
    flex_rules = [
        selectors
        for selectors, declarations in rules
        if "display:flex!important" in declarations
        and "width:100%!important" in declarations
        and "max-width:100%!important" in declarations
    ]
    assert len(flex_rules) == 1, "the native inner flex row must have one rule, without a late override"
    assert flex_rules[0] == inner_row_selectors
    assert ".dco-operator-form .form-tabs-list" not in flex_rules[0]

    # The outer shell is measured and assigned inline geometry by updateFixedTabs;
    # no important 100% width rule may target that shell itself.
    for selectors, declarations in rules:
        if "width:100%!important" not in declarations and "max-width:100%!important" not in declarations:
            continue
        for selector in selectors:
            if ".form-tabs-list" in selector:
                assert selector in inner_row_selectors, selector

    assert 'const tabs = frm && frm._dco_fixed_tabs' in text(HEADER)
    assert 'tabs.style.width = `${Math.round(align.width)}px`' in text(HEADER)

    # Keep the existing native list host and action spacing contract unchanged.
    assert 'node.closest("li,.nav-item") || node' in page_edit
    assert 'const parent = tabNode.parentElement' in page_edit
    assert 'host.tagName === "UL" || host.tagName === "OL"' in page_edit
    assert 'document.createElement(isList ? "li" : "div")' in page_edit
    assert "margin-inline-start:auto" in page_edit
    assert ".dco-operator-form .dco-tab-edit-toolbar-slot" in css
    assert "margin-inline-start: auto !important" in css
