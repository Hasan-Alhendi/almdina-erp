from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = APP_ROOT / "public" / "js" / "door_cutting_order_compact_measurements_ux.js"


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

    assert ".dco-fast-entry-toolbar{flex-wrap:nowrap !important" in source
    assert ".dco-fast-entry-toolbar>.dco-measurement-table-actions" in source
    assert "order:100;" in source
    assert "direction:ltr;" in source
    assert "width:32px !important;" in source
    assert "min-height:42px !important;" in source


def test_measurement_toolbar_reduces_visible_help_without_losing_guidance():
    source = _source()

    assert "dco-fast-tip" in source
    assert "dco-fast-info" in source
    assert "القشاط: نقرة" in source
    assert "الأسهم للتنقل بين الحقول" in source
    assert 'note.textContent = isArabic() ? "🔒 عرض فقط" : "🔒 Read only"' in source


def test_measurement_toolbar_polish_survives_dynamic_action_rendering():
    source = _source()

    assert "function observeToolbar(root)" in source
    assert "observer.observe(toolbar, { childList:true, subtree:true });" in source
    assert "polishToolbar(root);" in source
