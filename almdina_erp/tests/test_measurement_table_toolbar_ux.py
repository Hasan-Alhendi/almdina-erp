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


def test_measurement_toolbar_actions_are_kept_on_physical_left_in_rtl():
    source = _source()

    assert ".dco-fast-entry-toolbar > .dco-measurement-table-actions" in source
    assert "order:100;" in source
    assert "direction:ltr;" in source
    assert "width:36px !important;" in source


def test_measurement_toolbar_polish_survives_dynamic_action_rendering():
    source = _source()

    assert "function observeToolbar(root)" in source
    assert "observer.observe(toolbar, { childList:true, subtree:true });" in source
    assert "polishToolbar(root);" in source
