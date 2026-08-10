from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
SOURCE = APP_ROOT / "public" / "js" / "door_cutting_order_toolbar_stability_ux.js"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def test_measurement_toolbar_allows_only_title_and_two_actions():
    source = _source()

    assert "جدول قياسات الدرف" in source
    assert ".dco-fast-entry-toolbar > :not(.dco-fast-help):not(.dco-measurement-table-actions)" in source
    assert 'child.matches(".dco-print-measurements,.dco-open-measurements-window")' in source
    assert "if (child !== help && child !== actions) child.remove();" in source


def test_measurement_toolbar_contract_is_reapplied_after_dynamic_dom_changes():
    source = _source()

    assert "function reconcileMeasurementToolbar(frm)" in source
    assert "function observeMeasurementToolbar(frm)" in source
    assert "observer.observe(root, { childList: true, subtree: true });" in source
    assert "reconcileMeasurementToolbar(frm);" in source
