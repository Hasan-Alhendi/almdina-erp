from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "public" / "css" / "shop_floor_responsive.css"
QUICK_ACTIONS_PATH = ROOT / "public" / "js" / "shop_floor_quick_actions.js"
PAGE_PATH = (
    ROOT
    / "almdina_erp"
    / "page"
    / "shop_floor_inbox"
    / "shop_floor_inbox.js"
)


def test_shop_floor_styles_are_isolated_from_general_order_list() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".almdina-sf-order-card" in css
    assert ".almdina-sf-list" in css
    assert ".almdina-sf-tabs" in css

    # The worker inbox has its own presentation layer. The general DCO list
    # remains owned by door_cutting_order_responsive.css and keeps the laptop
    # table contract unchanged.
    assert ".dco-order-list" not in css
    assert ".list-row" not in css
    assert ".list-row-head" not in css


def test_shop_floor_cards_have_explicit_phone_and_tablet_layouts() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 720px)" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "grid-template-columns: 1fr;" in css
    assert "min-height: 48px !important;" in css


def test_shop_floor_statuses_have_distinct_visual_states() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")

    for status in ("Pending", "In Progress", "Paused", "Completed"):
        assert f'[data-status="{status}"]' in css

    assert ".sf-quick-action.is-loading" in css
    assert 'aria-busy="true"' in css
    assert "prefers-reduced-motion" in css


def test_quick_actions_load_the_dedicated_stylesheet_once() -> None:
    source = QUICK_ACTIONS_PATH.read_text(encoding="utf-8")

    assert "/assets/almdina_erp/css/shop_floor_responsive.css" in source
    assert 'SHOP_FLOOR_STYLESHEET_ID = "almdina-shop-floor-responsive-css"' in source
    assert "document.getElementById(SHOP_FLOOR_STYLESHEET_ID)" in source
    assert "ensureStylesheet();" in source


def test_shop_floor_defaults_to_a_route_aware_kanban_board() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    assert 'let mode = "board"' in source
    assert 'data-sf-mode="board"' in source
    assert "production_routes" in source
    assert 'data-drop-stage="${esc(stageType)}"' in source
    assert 'target !== (context.next || "__ready__")' in source
    assert "handoffStage(context)" in source
    assert ".almdina-sf-kanban" in css
    assert ".almdina-sf-kanban-column.is-drag-over" in css


def test_worker_list_keeps_assigned_work_first_and_completed_history_last() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    # The worker sees only their actionable current-stage assignments. Completed
    # history follows at the bottom and never exposes a production quick action.
    assert "function showsPersonalHistory()" in source
    assert "sessionContext.personal_inbox" in source
    assert "function isMyOperationalStage(row)" in source
    assert "actor_holds_current_stage_role" in source
    assert "function mergeVisibleList(activeRows, historyRows)" in source
    assert "? (activeRows || []).filter(isMyOperationalStage)" in source
    assert "return { assigned, completed };" in source
    assert "function workerBoardRows(activeRows)" in source
    assert 'listSection(__("الطلبات المنتهية"), completed, { completed: true })' in source
    assert 'terminal || completed ? "" : quickActionHtml(row)' in source
    assert 'completed ? " is-completed" : ""' in source

    # Completed history—not foreign-role work—owns the green full-row treatment.
    assert ".almdina-sf-list-title.is-completed" in css
    assert ".almdina-sf-order-card.is-completed" in css
    assert ".almdina-sf-order-card.is-completed[data-status]" in css
    assert "background: #dcfce7 !important;" in css
    assert "--sf-accent: #16a34a;" in css
    assert "is-other-role" not in css
    assert "is-other-role" not in source


def test_kanban_keeps_touch_users_on_explicit_server_authorized_actions() -> None:
    source = PAGE_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    assert "quickActionHtml(row)" in source
    assert "window.AlmdinaShopFloorQuickActions.perform" in source
    assert "can_handoff_stage === true" in source
    assert "get_handoff_context" in source
    assert "@media (max-width: 720px)" in css
    assert "grid-auto-columns: minmax(82vw, 82vw);" in css
