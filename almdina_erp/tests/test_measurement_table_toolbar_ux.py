from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
COMPACT = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_compact_measurements_ux.js"
)
ACTIONS = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
    / "door_cutting_order_measurement_actions_ux.js"
)


def _compact() -> str:
    return COMPACT.read_text(encoding="utf-8")


def _actions() -> str:
    return ACTIONS.read_text(encoding="utf-8")


def test_measurement_toolbar_icon_actions_are_owned_by_actions_ux():
    actions = _actions()

    assert "function decorateToolbarIconButton" in actions
    assert 'button.setAttribute("aria-label", resolvedLabel)' in actions
    assert "button.innerHTML = toolbarIconSvg(kind)" in actions
    assert 'kind: "print"' in actions
    assert 'kind: "expand"' in actions
    assert 'if (!button.querySelector("svg"))' in actions
    assert "printButton.textContent" not in actions
    assert "MutationObserver" not in actions.split("function ensureActions", 1)[1].split(
        "function schedule", 1
    )[0]


def test_measurement_toolbar_follows_page_direction_in_normal_flow():
    compact = _compact()

    assert ".dco-fast-entry-toolbar{" in compact
    assert "flex-wrap:wrap !important;" in compact
    assert ".dco-fast-entry-toolbar>.dco-measurement-table-actions" in compact
    assert "direction:inherit;" in compact
    assert "margin-inline-start:auto !important;" in compact
    assert "direction:ltr;" not in compact
    assert "width:32px !important;" in compact
    assert "min-height:42px !important;" in compact


def test_measurement_toolbar_shows_only_measurement_table_title():
    compact = _compact()

    assert '__("Door Measurements Table")' in compact
    assert "جدول قياسات الدرف" not in compact
    assert 'class="dco-measurement-title"' in compact
    assert ".dco-fast-entry-toolbar>.dco-fast-readonly-note" in compact
    assert ".dco-fast-entry-toolbar>.dco-order-edge-color-badge" in compact
    assert "display:none !important;" in compact
    assert "إدخال سريع:" not in compact
    assert "القشاط: نقرة" not in compact
    assert "الأسهم للتنقل بين الحقول" not in compact


def test_compact_toolbar_polish_does_not_rewrite_action_icons():
    compact = _compact()

    assert "function polishToolbar(root)" in compact
    assert "compactReadonlyNote(root);" in compact
    assert 'printButton.innerHTML = toolbarIconSvg("print")' not in compact
    assert 'openButton.innerHTML = toolbarIconSvg("expand")' not in compact
    assert "compactIconReady" not in compact
