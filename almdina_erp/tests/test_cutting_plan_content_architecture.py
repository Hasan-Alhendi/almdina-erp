from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
CONTENT = CUTTING_PLAN / "door_cutting_order_plan_content_ux.js"
STYLES = CUTTING_PLAN / "door_cutting_order_plan_content_styles.js"
PRESENTER = CUTTING_PLAN / "door_cutting_order_plan_board_presenter.js"
ASSET_REGISTRY = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_workspace_asset_registry.js"
)


def test_plan_content_runtime_order_keeps_local_owners_adjacent_to_orchestrator():
    source = ASSET_REGISTRY.read_text(encoding="utf-8")
    styles = "door_cutting_order_plan_content_styles.js"
    presenter = "door_cutting_order_plan_board_presenter.js"
    content = "door_cutting_order_plan_content_ux.js"
    tabs = "door_cutting_order_plan_tabs_ux.js"
    for asset in (styles, presenter, content, tabs):
        assert asset in source
    assert source.index(styles) < source.index(presenter) < source.index(content) < source.index(tabs)


def test_plan_content_is_an_orchestrator_not_a_style_or_focus_owner():
    source = CONTENT.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 600
    assert "style.textContent" not in source
    assert "function desiredBoardColumns" not in source
    assert "function openBoardFocus" not in source
    assert "AlmdinaPlanContentStyles" in source
    assert "AlmdinaPlanBoardPresenter" in source
    assert "presenter.layoutBoardGallery(planRoot)" in source
    assert "presenter.installInteractions(root)" in source


def test_style_owner_preserves_existing_style_identity_and_critical_selectors():
    source = STYLES.read_text(encoding="utf-8")
    assert 'const STYLE_ID = "dco-plan-content-layout-css-v7"' in source
    for selector in (
        ".dco-plan-actions-section",
        ".dco-margin-policy-alert",
        ".dco-board-gallery",
        ".dco-board-focus__dialog",
        "@media (max-width:760px)",
        "@media (max-width:520px)",
    ):
        assert selector in source
    assert "gap:8px !important" in source
    assert "document.head.appendChild(style)" in source


def test_board_presenter_owns_gallery_layout_focus_and_interactions_without_frappe_hooks():
    source = PRESENTER.read_text(encoding="utf-8")
    for contract in (
        "function desiredBoardColumns(width)",
        "function layoutBoardGallery(planRoot)",
        "function openBoardFocus(card)",
        "function installInteractions(root)",
        "FOCUS_INITIAL_ZOOM = 1.25",
        "FOCUS_MIN_ZOOM = 1",
        "FOCUS_MAX_ZOOM = 2",
        "FOCUS_ZOOM_STEP = 0.25",
    ):
        assert contract in source
    assert "frappe.ui.form.on" not in source
    assert "AlmdinaDocumentContext" not in source


def test_orchestrator_public_api_and_document_lifecycle_contract_stay_stable():
    source = CONTENT.read_text(encoding="utf-8")
    for contract in (
        "window.AlmdinaPlanContentUX = Object.freeze",
        "apply,",
        "cleanRenderedPlan,",
        "isReady,",
        "parsePlanSnapshot,",
        'scheduleFrame(frm, "plan-content-apply-frame"',
        'schedule(frm, "plan-content-apply-delay"',
        "}, 350);",
        'scheduleFrame(frm, "plan-content-observer-frame"',
        'scheduleFrame(frm, "plan-content-resize-frame"',
        'context.registerObserver(frm, "plan-content-observer", observer)',
        'context.registerObserver(frm, "plan-content-resize-observer", observer)',
    ):
        assert contract in source
