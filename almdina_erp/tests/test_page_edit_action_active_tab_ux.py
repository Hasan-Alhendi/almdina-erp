from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_EDIT_ACTION = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_page_edit_action_ux.js"
)


def test_page_edit_action_uses_frappe_selected_tab_not_layout_build_cursor() -> None:
    source = PAGE_EDIT_ACTION.read_text(encoding="utf-8")

    assert 'typeof frm.get_active_tab === "function"' in source
    assert "frm.get_active_tab()" in source
    assert "frm.layout.current_tab" not in source
    assert 'results_tab: "plan"' in source
    assert 'cost_tab: "cost"' in source
