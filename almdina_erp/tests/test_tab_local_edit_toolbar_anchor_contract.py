from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
PAGE_EDIT = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_page_edit_action_ux.js"
)


def test_tab_local_toolbar_mounts_in_the_native_frappe_tab_list():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    # The refactored toolbar shares the native tab-list row rather than mounting
    # three duplicate controls beside individual Section Break wrappers.
    assert "function toolbarSlotHost(frm)" in source
    assert 'node.closest("li,.nav-item") || node' in source
    assert "const parent = tabNode.parentElement" in source
    assert 'host.tagName === "UL" || host.tagName === "OL"' in source
    assert 'document.createElement(isList ? "li" : "div")' in source


def test_one_toolbar_tracks_the_active_top_level_tab():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    assert 'order_tab: "order"' in source
    assert 'results_tab: "plan"' in source
    assert 'cost_tab: "cost"' in source
    assert "slot.replaceChildren(toolbar)" in source
    assert "renderToolbar(frm, activeKind(frm));" in source
