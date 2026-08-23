from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOBILE_LIST_CSS = ROOT / "public" / "css" / "door_cutting_order_mobile_list.css"
LIST_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mobile_card_matches_approved_reference_hierarchy() -> None:
    css = source(MOBILE_LIST_CSS)
    js = source(LIST_UX)

    # Card-only scope: desktop/table presentation must remain outside this layer.
    assert ".dco-order-list.dco-order-card-layout" in css
    assert ".dco-order-list:not(.dco-order-card-layout)" not in css

    # Reference hierarchy: customer + status, clickable order ID, three equal
    # information tiles, full-width date, then one state-aware CTA.
    for marker in (
        'class="dco-card-customer-block"',
        'class="dco-card-state-pill"',
        'class="dco-card-order-link"',
        'class="dco-card-info-grid"',
        'class="dco-card-date-row"',
    ):
        assert marker in js

    assert 'renderInfoTile("لون اللوح", model.boardColor' in js
    assert 'renderInfoTile("لون القشاط", model.edgeColor' in js
    assert 'renderInfoTile("نوع القشاط", model.edgeType' in js
    assert '"default_edge_type"' in js
    assert 'class="dco-card-workflow"' not in js
    assert 'class="dco-card-assignee"' not in js

    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert ".dco-card-date-row" in css
    assert ".dco-card-production-action.is-start" in css
    assert ".dco-card-production-action.is-finish" in css
    assert ".dco-card-complete-state" in css

    # The three approved visual states have separate themes.
    assert ".dco-mobile-order-card.is-ready" in css
    assert ".dco-mobile-order-card.is-progress" in css
    assert ".dco-mobile-order-card.is-completed" in css
    assert 'label: __("جاهز للبدء")' in js
    assert 'label: __("قيد التنفيذ")' in js
    assert 'label: __("تم الإنجاز")' in js


def test_mobile_card_keeps_server_authorized_actions_as_the_only_action_source() -> None:
    js = source(LIST_UX)

    assert "const quickActions = window.AlmdinaShopFloorQuickActions" in js
    assert "quickActions.actionFor(context)" in js
    assert "authorized.canStart === true" in js
    assert "authorized.canHandoff === true" in js
    assert "quickActions.perform(context" in js
    assert "frappe.confirm(" in js
