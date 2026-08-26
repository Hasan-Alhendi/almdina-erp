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
MODULE_ROOT = ROOT / "public" / "js" / "shop_floor_inbox"
STATE_PATH = MODULE_ROOT / "state.js"
VIEW_MODEL_PATH = MODULE_ROOT / "view_model.js"
RENDERER_PATH = MODULE_ROOT / "renderer.js"
INTERACTIONS_PATH = MODULE_ROOT / "interactions.js"
API_PATH = MODULE_ROOT / "api.js"
CONTROLLER_PATH = MODULE_ROOT / "controller.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shop_floor_styles_are_isolated_from_general_order_list() -> None:
    css = source(CSS_PATH)

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
    css = source(CSS_PATH)

    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 720px)" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert "grid-template-columns: 1fr;" in css
    assert "min-height: 48px !important;" in css


def test_shop_floor_statuses_have_distinct_visual_states() -> None:
    css = source(CSS_PATH)

    for status in ("Pending", "In Progress", "Paused", "Completed"):
        assert f'[data-status="{status}"]' in css

    assert ".sf-quick-action.is-loading" in css
    assert 'aria-busy="true"' in css
    assert "prefers-reduced-motion" in css


def test_quick_actions_load_the_dedicated_stylesheet_once() -> None:
    quick_actions = source(QUICK_ACTIONS_PATH)

    assert "/assets/almdina_erp/css/shop_floor_responsive.css" in quick_actions
    assert 'SHOP_FLOOR_STYLESHEET_ID = "almdina-shop-floor-responsive-css"' in quick_actions
    assert "document.getElementById(SHOP_FLOOR_STYLESHEET_ID)" in quick_actions
    assert "ensureStylesheet();" in quick_actions


def test_shop_floor_defaults_to_a_route_aware_kanban_board() -> None:
    page = source(PAGE_PATH)
    state = source(STATE_PATH)
    view_model = source(VIEW_MODEL_PATH)
    renderer = source(RENDERER_PATH)
    interactions = source(INTERACTIONS_PATH)
    controller = source(CONTROLLER_PATH)
    css = source(CSS_PATH)

    assert 'mode: "board"' in state
    assert 'data-sf-mode="board"' in renderer
    assert "production_routes" in view_model
    assert 'data-drop-stage="${esc(stageType)}"' in renderer
    assert 'target !== (context.next || "__ready__")' in interactions
    assert "actions.handoff(context)" in interactions
    assert "function handoff(context)" in controller
    assert "/assets/almdina_erp/js/shop_floor_inbox/state.js" in page
    assert "/assets/almdina_erp/js/shop_floor_inbox/renderer.js" in page
    assert ".almdina-sf-kanban" in css
    assert ".almdina-sf-kanban-column.is-drag-over" in css


def test_worker_list_keeps_assigned_work_first_and_completed_history_last() -> None:
    view_model = source(VIEW_MODEL_PATH)
    renderer = source(RENDERER_PATH)
    css = source(CSS_PATH)

    # The worker sees only their actionable current-stage assignments. Completed
    # history follows at the bottom only when the backend history capability says
    # it is visible, and it never exposes a production quick action.
    assert "function showsPersonalHistory(context)" in view_model
    assert "context && context.personal_inbox" in view_model
    assert "function canViewHistory(context)" in view_model
    assert "context && context.can_view_history === true" in view_model
    assert "function isMyOperationalStage(row)" in view_model
    assert "actor_holds_current_stage_role === true" in view_model
    assert "function mergeVisibleList(activeRows, historyRows, context)" in view_model
    assert "? asRows(activeRows).filter(isMyOperationalStage)" in view_model
    assert "return { assigned, completed, canViewHistory: canViewHistory(context) };" in view_model
    assert "function workerBoardRows(activeRows, context)" in view_model
    assert 'listSection(__("الطلبات المنتهية"), model.completed, mode, { completed: true })' in renderer
    assert 'terminal || completed ? "" : quickActionHtml(row, mode)' in renderer
    assert 'completed ? " is-completed" : ""' in renderer

    # Completed history—not foreign-role work—owns the green full-row treatment.
    assert ".almdina-sf-list-title.is-completed" in css
    assert ".almdina-sf-order-card.is-completed" in css
    assert ".almdina-sf-order-card.is-completed[data-status]" in css
    assert "background: #dcfce7 !important;" in css
    assert "--sf-accent: #16a34a;" in css
    assert "is-other-role" not in css
    assert "is-other-role" not in view_model
    assert "is-other-role" not in renderer


def test_kanban_keeps_touch_users_on_explicit_server_authorized_actions() -> None:
    renderer = source(RENDERER_PATH)
    view_model = source(VIEW_MODEL_PATH)
    api = source(API_PATH)
    controller = source(CONTROLLER_PATH)
    css = source(CSS_PATH)

    assert "function quickActionHtml(row, mode)" in renderer
    assert "AlmdinaShopFloorQuickActions" in renderer
    assert "quickActions.perform" in controller
    assert "can_handoff_stage === true" in view_model
    assert "get_handoff_context" in api
    assert "@media (max-width: 720px)" in css
    assert "grid-auto-columns: minmax(82vw, 82vw);" in css
