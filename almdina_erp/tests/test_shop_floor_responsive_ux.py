from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS_PATH = ROOT / "public" / "css" / "shop_floor_responsive.css"
QUICK_ACTIONS_PATH = ROOT / "public" / "js" / "shop_floor_quick_actions.js"


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
