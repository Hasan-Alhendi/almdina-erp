from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_compact_measurements_ux.js"
)


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_measurement_toolbar_uses_compact_accessible_icon_actions():
    source = _source()

    assert 'classList.add("dco-toolbar-icon-button")' in source
    assert 'printButton.setAttribute("aria-label", label)' in source
    assert 'openButton.setAttribute("aria-label", label)' in source
    assert 'printButton.innerHTML = toolbarIconSvg("print")' in source
    assert 'openButton.innerHTML = toolbarIconSvg("expand")' in source


def test_measurement_toolbar_is_single_row_and_actions_stay_on_physical_left():
    source = _source()

    assert ".dco-fast-entry-toolbar{" in source
    assert "flex-wrap:nowrap !important;" in source
    assert ".dco-fast-entry-toolbar>.dco-measurement-table-actions" in source
    assert "order:100;" in source
    assert "direction:ltr;" in source
    assert "width:32px !important;" in source
    assert "min-height:42px !important;" in source


def test_measurement_toolbar_shows_only_measurement_table_title():
    source = _source()

    assert "جدول قياسات الدرف" in source
    assert "Door Measurements Table" in source
    assert 'class="dco-measurement-title"' in source
    assert ".dco-fast-entry-toolbar>.dco-fast-readonly-note" in source
    assert ".dco-fast-entry-toolbar>.dco-order-edge-color-badge" in source
    assert "display:none !important;" in source
    assert "إدخال سريع:" not in source
    assert "القشاط: نقرة" not in source
    assert "الأسهم للتنقل بين الحقول" not in source


def test_measurement_toolbar_polish_survives_dynamic_action_rendering():
    source = _source()

    assert "function observeToolbar(root)" in source
    assert "observer.observe(toolbar, { childList:true, subtree:true });" in source
    assert "polishToolbar(root);" in source
