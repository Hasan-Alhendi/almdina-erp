from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
RESPONSIVE_CSS = ROOT / "public" / "css" / "door_cutting_order_responsive.css"
OPERATOR_UX = ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
BULK_ROWS_UX = ROOT / "public" / "js" / "door_cutting_order_bulk_rows_ux.js"
LIST_UX = ROOT / "public" / "js" / "door_cutting_order_list.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_responsive_presentation_is_a_scoped_stylesheet_not_an_extra_form_controller():
    hooks = source(HOOKS)
    css = source(RESPONSIVE_CSS)

    assert 'app_include_css = [' in hooks
    assert '"/assets/almdina_erp/css/door_cutting_order_responsive.css"' in hooks
    assert ".dco-operator-form" in css
    assert ".dco-order-list" in css
    assert ".page-head.dco-responsive-head" in css
    assert "frappe.ui.form.on" not in css
    assert "MutationObserver" not in css


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

    phone = css.split("@media (max-width: 720px)", 1)[1].split(
        "@media (max-width: 480px)", 1
    )[0]
    assert ".dco-fast-table tbody tr" in phone
    assert "display: grid !important" in phone
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in phone
    assert "min-width: 0 !important" in phone
    assert "content: attr(data-label)" in phone
    assert "width: 940px" not in phone
    assert "min-width: 940px" not in phone

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
    assert ".dco-edge-buttons" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important" in css
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
