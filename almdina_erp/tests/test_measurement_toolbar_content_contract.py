from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = APP_ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_toolbar_stability_ux.js"
PRESENTATION_CSS = APP_ROOT / "public" / "css" / "door_cutting_order_form_presentation.css"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _css() -> str:
    return PRESENTATION_CSS.read_text(encoding="utf-8")


def test_measurement_toolbar_allows_only_centered_title_and_three_actions():
    source = _source()
    css = _css()

    assert "جدول قياسات الدرف" in source
    assert "justify-content:center!important;" in css
    assert "position:absolute!important;" in css
    assert "left:8px!important;" in css
    assert ".dco-fast-entry-toolbar > :not(.dco-fast-help):not(.dco-measurement-table-actions)" in css
    assert 'child.matches(".dco-print-measurements,.dco-open-measurements-window,.dco-input-help")' in source
    assert "if (child !== help && child !== actions) child.remove();" in source


def test_measurement_help_action_contains_previous_entry_guidance():
    source = _source()

    assert "function ensureMeasurementHelpAction(actions)" in source
    assert 'button.className = "btn btn-default btn-sm dco-input-help"' in source
    assert "تعليمات إدخال القياسات" in source
    assert "العرض ثم <kbd>Tab</kbd>" in source
    assert "الطول ثم <kbd>Enter</kbd>" in source
    assert "استخدم الأسهم ← ↑ ↓ →" in source
    assert "نقرتان على الضلع لاختيار نوع القشاط" in source
    assert "الخصم النهائي يُحسب حسب سماكة القشاط في كل ضلع" in source


def test_existing_print_and_separate_window_actions_are_not_reimplemented_here():
    source = _source()

    assert "dco-print-measurements" in source
    assert "dco-open-measurements-window" in source
    assert "printMeasurements(" not in source
    assert "openEditableMeasurements(" not in source


def test_measurement_toolbar_contract_is_reapplied_after_dynamic_dom_changes():
    source = _source()

    assert "function reconcileMeasurementToolbar(frm)" in source
    assert "function observeMeasurementToolbar(frm)" in source
    assert "observer.observe(root, { childList: true, subtree: true });" in source
    assert "reconcileMeasurementToolbar(frm);" in source
