from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOBILE_LIST_CSS = ROOT / "public" / "css" / "door_cutting_order_mobile_list.css"


def source() -> str:
    return MOBILE_LIST_CSS.read_text(encoding="utf-8")


def test_mobile_card_visual_contract_matches_approved_hierarchy() -> None:
    css = source()

    # Keep this visual layer mobile-only; desktop Frappe list must remain untouched.
    assert ".dco-order-list.dco-order-card-layout" in css

    # Customer and tappable order ID are the primary header anchors.
    assert 'grid-template-areas:' in css
    assert '"customer order"' in css
    assert '.dco-card-customer::before' in css
    assert 'content: "اسم العميل"' in css
    assert '.dco-card-order-link::before' in css
    assert 'content: "ID الطلب"' in css

    # The information area follows the approved two-column card rhythm instead
    # of the old compressed/wide-row presentation.
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert ".dco-card-wide-field" in css
    assert "grid-column: auto" in css
    assert "min-height: 72px" in css

    # Start/finish are a single strong CTA and completed work has its own green state.
    assert ".dco-card-production-action.is-start" in css
    assert ".dco-card-production-action.is-finish" in css
    assert "min-height: 54px" in css
    assert ".dco-card-complete-state" in css
    assert ".dco-mobile-order-card.dco-list-row-completed" in css
