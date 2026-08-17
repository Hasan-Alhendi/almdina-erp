from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = ROOT / "public" / "js"
PUBLIC_CSS = ROOT / "public" / "css"
RESPONSIVE_CSS = PUBLIC_CSS / "shop_floor_responsive.css"
MOBILE_LIST_CSS = PUBLIC_CSS / "door_cutting_order_mobile_list.css"
LIST_UX = PUBLIC_JS / "door_cutting_order" / "list_view" / "door_cutting_order_list.js"
QUICK_ACTIONS_UX = PUBLIC_JS / "shop_floor_quick_actions.js"
SHOP_FLOOR_INBOX = ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js"
SHOP_FLOOR_RENDERER = PUBLIC_JS / "shop_floor_inbox" / "renderer.js"
HOOKS = ROOT / "frontend_assets.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phone_breakpoint_is_reserved_for_cards_and_tablet_keeps_table():
    css = source(RESPONSIVE_CSS)
    mobile_css = source(MOBILE_LIST_CSS)
    list_source = source(LIST_UX)

    assert '(max-width: 600px)' in mobile_css
    assert '.dco-order-list.dco-order-card-layout' in mobile_css
    assert 'matchMedia("(max-width: 600px)")' in list_source
    assert '.dco-order-list:not(.dco-order-card-layout)' in css
    assert 'min-width: 980px' in css


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

    # Leaving phone/card mode must restore Frappe's native table cleanly. The
    # incremental renderer removes generated cards before returning instead of
    # relying on a literal one-line guard that could leave stale card DOM behind.
    assert 'if (!applyCardLayoutClass(listview)) {' in list_source
    assert "containers.forEach(removeMobileCard);" in list_source
    assert "ensureMobileCardStylesheet();" in list_source
    assert 'MOBILE_CARD_STYLESHEET_HREF = "/assets/almdina_erp/css/door_cutting_order_mobile_list.css?v=4"' in list_source
    assert ".dco-order-list.dco-order-card-layout" in mobile_css
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
    assert "min-width: 980px" in css

    assert '"/assets/almdina_erp/js/shop_floor_quick_actions.js"' in hooks
    assert "services.shop_floor_commands.start_my_stage" in quick_actions
    assert "services.shop_floor_commands.handoff_to_next" in quick_actions
    assert "frappe.db.set_value" not in quick_actions
    assert "/assets/almdina_erp/js/shop_floor_inbox/renderer.js" in inbox_page
    assert "sf-quick-action" in inbox_renderer
    assert 'row.edge_color || "—"' in inbox_renderer


def test_mobile_card_does_not_replace_desktop_table_markup():
    css = source(RESPONSIVE_CSS)
    list_source = source(LIST_UX)

    assert "dco-order-card-container" in list_source
    assert ".dco-order-card-container > .list-row" in css
    assert ".dco-order-list:not(.dco-order-card-layout)" in css
    assert "min-width: 980px" in css


def test_mobile_card_keeps_factory_fields_and_removes_old_large_workflow_sections():
    list_source = source(LIST_UX)

    for field in ("customer", "board_description", "edge_color", "default_edge_type", "order_date"):
        assert field in list_source
    assert "dco-card-workflow" not in list_source
    assert "dco-card-assignee" not in list_source


def test_completed_mobile_card_is_visually_terminal_and_has_no_action_button():
    list_source = source(LIST_UX)
    mobile_css = source(MOBILE_LIST_CSS)

    assert 'state.key === "completed"' in list_source
    assert 'class="dco-card-complete-state"' in list_source
    assert ".dco-mobile-order-card.is-completed" in mobile_css
    assert ".dco-card-complete-state" in mobile_css
