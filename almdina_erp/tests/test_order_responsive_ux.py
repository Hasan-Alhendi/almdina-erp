from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
RESPONSIVE_CSS = ROOT / "public" / "css" / "door_cutting_order_responsive.css"
MOBILE_CARDS_UX = ROOT / "public" / "js" / "door_cutting_order_mobile_cards_ux.js"
OPERATOR_UX = ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
BULK_ROWS_UX = ROOT / "public" / "js" / "door_cutting_order_bulk_rows_ux.js"
LIST_UX = ROOT / "public" / "js" / "door_cutting_order_list.js"


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
    assert '"public/js/door_cutting_order_mobile_cards_ux.js"' in hooks
    assert hooks.index('"public/js/input_stability.js"') < hooks.index(
        '"public/js/door_cutting_order_mobile_cards_ux.js"'
    )
    assert "ResizeObserver" in cards
    assert "MutationObserver" not in cards


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
    cards = source(MOBILE_CARDS_UX)
    operator = source(OPERATOR_UX)
    bulk = source(BULK_ROWS_UX)

    assert ".dco-mobile-piece-cards .dco-fast-table tbody tr" in cards
    assert "display:grid!important" in cards
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in cards
    assert "min-width:0!important" in cards
    assert "content:attr(data-label)" in cards
    assert "width:940px" not in cards
    assert "min-width:940px" not in cards

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
    cards = source(MOBILE_CARDS_UX)

    assert "--dco-touch-target: 44px" in css
    assert "min-height: var(--dco-touch-target)" in css
    assert "--dco-card-touch-target:44px" in cards
    assert ".dco-edge-buttons" in cards
    assert "grid-template-columns:repeat(2,minmax(0,1fr))!important" in cards
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


def test_card_activation_uses_actual_available_width_not_only_a_media_query():
    cards = source(MOBILE_CARDS_UX)

    assert "const CARD_MAX_WIDTH = 900" in cards
    assert "document.documentElement.clientWidth" in cards
    assert "window.innerWidth" in cards
    assert "window.screen && window.screen.width" in cards
    assert "root && root.getBoundingClientRect().width" in cards
    assert "Math.min(...widths)" in cards
    assert 'root.classList.toggle("dco-mobile-piece-cards", shouldUseCardLayout(root))' in cards
