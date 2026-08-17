from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "frontend_assets.py"
RESPONSIVE_CSS = ROOT / "public" / "css" / "door_cutting_order_responsive.css"
MOBILE_LIST_CSS = ROOT / "public" / "css" / "door_cutting_order_mobile_list.css"
RESPONSIVE_DEVICE = ROOT / "public" / "js" / "responsive_device.js"
MOBILE_CARDS_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "responsive"
    / "door_cutting_order_mobile_cards_ux.js"
)
OPERATOR_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_operator_ux.js"
)
BULK_ROWS_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_bulk_rows_ux.js"
)
LIST_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)
QUICK_ACTIONS_UX = ROOT / "public" / "js" / "shop_floor_quick_actions.js"
SHOP_FLOOR_INBOX = (
    ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js"
)
SHOP_FLOOR_RENDERER = ROOT / "public" / "js" / "shop_floor_inbox" / "renderer.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_responsive_presentation_uses_scoped_css_and_a_focused_card_adapter():
    hooks = source(HOOKS)
    css = source(RESPONSIVE_CSS)
    cards = source(MOBILE_CARDS_UX)

    assert 'app_include_css = [' in hooks
    assert '"/assets/almdina_erp/css/door_cutting_order_responsive.css"' in hooks
    assert ".dco-operator-form" in css
    assert ".dco-order-list" in css
    assert ".page-head.dco-responsive-head" in css
    assert "frappe.ui.form.on" not in css
    assert "MutationObserver" not in css
    assert '"public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js"' in hooks
    assert '"/assets/almdina_erp/js/responsive_device.js"' in hooks
    assert hooks.index('"public/js/input_stability.js"') < hooks.index(
        '"public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js"'
    )
    assert "ResizeObserver" in cards
    assert "MutationObserver" not in cards
    assert "const CARD_CSS" not in cards
    assert ".dco-mobile-piece-cards" in css


def test_layout_has_explicit_desktop_tablet_phone_and_small_phone_breakpoints():
    css = source(RESPONSIVE_CSS)

    for breakpoint in (
        "@media (max-width: 1200px)",
        "@media (max-width: 900px)",
        "@media (max-width: 720px)",
        "@media (max-width: 480px)",
    ):
        assert breakpoint in css
    assert "orientation: landscape" in css


def test_phone_measurements_use_labelled_cards_without_fixed_table_width():
    css = source(RESPONSIVE_CSS)
    operator = source(OPERATOR_UX)
    bulk = source(BULK_ROWS_UX)

    assert ".dco-mobile-piece-cards .dco-fast-table tbody tr" in css
    assert "grid-template-columns: repeat(6, minmax(0, 1fr))" in css
    assert ".dco-col-width" in css
    assert ".dco-col-length" in css
    assert ".dco-col-qty" in css
    assert "grid-row: 2" in css
    assert "content: attr(data-label)" in css
    assert 'class="dco-help-secondary"' in operator
    assert "width:940px" not in css
    assert "min-width:940px" not in css

    for label_key in (
        "labels.row",
        "labels.type",
        "labels.width",
        "labels.length",
        "labels.quantity",
        "labels.rotation",
        "labels.edges",
        "labels.edgeType",
        "labels.shape",
        "labels.notes",
        "labels.remove",
    ):
        assert f'data-label="${{{label_key}}}"' in operator
    assert 'cell.dataset.label = isArabic() ? "تحديد السطر" : "Select row"' in bulk


def test_phone_controls_are_touch_sized_and_primary_surfaces_stack():
    css = source(RESPONSIVE_CSS)

    assert "--dco-touch-target: 44px" in css
    assert "min-height: var(--dco-touch-target)" in css
    assert "--dco-piece-control-height: 42px" in css
    assert ".dco-edge-buttons" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important" in css
    assert "min-height:48px!important" not in css
    assert ".dco-status-strip" in css
    assert ".dco-cost-kpis" in css
    assert "grid-template-columns: 1fr !important" in css


def test_order_header_tabs_dialogs_and_list_are_viewport_safe():
    css = source(RESPONSIVE_CSS)
    list_source = source(LIST_UX)

    assert ".page-head.dco-responsive-head .page-actions" in css
    assert ".dco-sticky-tabs" in css
    assert "overflow-x: auto !important" in css
    assert ".dco-special-shape-modal .modal-dialog" in css
    assert ".dco-clipped-corner-modal .modal-dialog" in css
    assert ".dco-large-notes-dialog .modal-dialog" in css
    assert "100dvh" in css
    assert 'root.classList.add("dco-order-list")' in list_source


def test_accessibility_preferences_remain_first_class():
    css = source(RESPONSIVE_CSS)

    assert ":focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "overscroll-behavior-inline: contain" in css
    assert "-webkit-overflow-scrolling: touch" in css


def test_measurement_cards_activate_only_for_a_phone_not_a_narrow_laptop_panel():
    cards = source(MOBILE_CARDS_UX)
    responsive = source(RESPONSIVE_DEVICE)

    assert "const PHONE_SHORT_SIDE_MAX_WIDTH = 600" in responsive
    assert "const PHONE_VIEWPORT_MAX_WIDTH = 900" in responsive
    assert "document.documentElement && document.documentElement.clientWidth" in responsive
    assert "window.innerWidth" in responsive
    assert "window.screen && window.screen.width" in responsive
    assert "window.screen && window.screen.height" in responsive
    assert "function deviceShortSide()" in responsive
    assert "root && root.getBoundingClientRect" in responsive
    assert "Math.min(...widths)" in responsive
    assert "viewport <= PHONE_SHORT_SIDE_MAX_WIDTH" in responsive
    assert "deviceShortSide() <= PHONE_SHORT_SIDE_MAX_WIDTH" in responsive
    assert "window.AlmdinaResponsiveDevice" in cards
    assert 'root.classList.toggle("dco-mobile-piece-cards", shouldUseCardLayout(root))' in cards


def test_mobile_order_list_uses_reference_card_and_server_authorized_actions():
    css = source(RESPONSIVE_CSS)
    mobile_css = source(MOBILE_LIST_CSS)
    list_source = source(LIST_UX)
    quick_actions = source(QUICK_ACTIONS_UX)
    inbox_page = source(SHOP_FLOOR_INBOX)
    inbox_renderer = source(SHOP_FLOOR_RENDERER)
    hooks = source(HOOKS)

    assert "window.AlmdinaResponsiveDevice" in list_source
    assert "usesCardLayout" in list_source
    assert 'root.classList.toggle("dco-order-card-layout"' in list_source
    assert 'node.matches(".list-row-container")' in list_source
    assert 'class="dco-mobile-order-card' in list_source
    assert 'class="dco-card-customer-block"' in list_source
    assert 'class="dco-card-state-pill"' in list_source
    assert 'class="dco-card-order-link"' in list_source
    assert 'class="dco-card-info-grid"' in list_source
    assert 'renderInfoTile("لون اللوح", model.boardColor' in list_source
    assert 'renderInfoTile("لون القشاط", model.edgeColor' in list_source
    assert 'renderInfoTile("نوع القشاط", model.edgeType' in list_source
    assert '"default_edge_type"' in list_source
    assert 'class="dco-card-workflow"' not in list_source
    assert 'class="dco-card-assignee"' not in list_source
    assert "const quickActions = window.AlmdinaShopFloorQuickActions" in list_source
    assert "quickActions.perform" in list_source
    assert 'matchMedia("(max-width: 600px)")' in list_source
    assert 'if (!applyCardLayoutClass(listview)) return;' in list_source
    assert "ensureMobileCardStylesheet();" in list_source
    assert 'MOBILE_CARD_STYLESHEET_HREF = "/assets/almdina_erp/css/door_cutting_order_mobile_list.css?v=5"' in list_source
    assert ".dco-order-list.dco-order-card-layout" in mobile_css
    scoped_result_rule = mobile_css.split(
        ".dco-order-list.dco-order-card-layout .result {",
        1,
    )[1].split("}", 1)[0]
    assert "height: auto !important;" in scoped_result_rule
    assert "min-height: 100%;" in scoped_result_rule
    assert "max-height:" not in scoped_result_rule
    assert "overflow: hidden" not in scoped_result_rule
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in mobile_css
    assert ".dco-card-production-action.is-start" in mobile_css
    assert ".dco-card-production-action.is-finish" in mobile_css
    assert ".dco-card-complete-state" in mobile_css
    assert ".dco-mobile-order-card.is-ready" in mobile_css
    assert ".dco-mobile-order-card.is-progress" in mobile_css
    assert ".dco-mobile-order-card.is-completed" in mobile_css
    assert ".dco-order-card-container > .list-row" in css
    assert ".dco-order-list.dco-order-card-layout .dco-mobile-order-card" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert ".dco-order-list:not(.dco-order-card-layout)" in css
    assert ".dco-order-list:not(.dco-order-card-layout)" not in mobile_css
    assert "min-width: 980px" in css

    assert '"/assets/almdina_erp/js/shop_floor_quick_actions.js"' in hooks
    assert "services.shop_floor_commands.start_my_stage" in quick_actions
    assert "services.shop_floor_commands.handoff_to_next" in quick_actions
    assert "frappe.db.set_value" not in quick_actions
    assert "/assets/almdina_erp/js/shop_floor_inbox/renderer.js" in inbox_page
    assert "sf-quick-action" in inbox_renderer
    assert 'row.edge_color || "—"' in inbox_renderer
    assert 'row.board_description || "—"' in inbox_renderer


def test_desk_list_prioritizes_active_then_ready_then_completed_rows_green():
    css = source(RESPONSIVE_CSS)
    list_source = source(LIST_UX)

    assert "function applyOperationalRoleRows(listview)" in list_source
    assert "get_order_operational_role_flags" in list_source
    assert "function personalQueueState(doc, flag = {})" in list_source
    assert 'if (flag.assignment_state === "completed") return "completed";' in list_source
    assert 'return "in_progress";' in list_source
    assert 'return "ready";' in list_source
    assert "function sortPersonalQueueItems(items)" in list_source
    assert '"assignment_time"' in list_source
    assert '"completion_time"' in list_source
    assert "return [...inProgress, ...ready, ...completed];" in list_source
    assert "const ordered = sortPersonalQueueItems(queueItems).map(item => item.container);" in list_source
    assert 'classList.toggle("dco-list-row-completed"' in list_source
    assert "const needsReorder = ordered.some" in list_source
    assert "ordered.forEach(container => result.appendChild(container));" in list_source
    assert ".list-row-container.dco-list-row-completed > .list-row" in css
    assert ".list-row-container.dco-list-row-completed > .list-row .list-row-col" in css
    assert "background: #dcfce7 !important;" in css
