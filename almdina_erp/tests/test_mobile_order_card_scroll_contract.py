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


def test_mobile_cards_are_not_clipped_by_frappe_pre_card_result_height() -> None:
    css = source(MOBILE_LIST_CSS)

    scoped_result_rule = css.split(
        ".dco-order-list.dco-order-card-layout .result {",
        1,
    )[1].split("}", 1)[0]

    assert "height: auto !important;" in scoped_result_rule
    assert "min-height: 100%;" in scoped_result_rule
    assert "max-height:" not in scoped_result_rule
    assert "overflow: hidden" not in scoped_result_rule


def test_mobile_scroll_fix_is_cache_busted_without_changing_desktop_layout() -> None:
    css = source(MOBILE_LIST_CSS)
    list_source = source(LIST_UX)

    assert 'MOBILE_CARD_STYLESHEET_HREF = "/assets/almdina_erp/css/door_cutting_order_mobile_list.css?v=5"' in list_source
    assert ".dco-order-list.dco-order-card-layout .result" in css
    assert ".dco-order-list:not(.dco-order-card-layout)" not in css
