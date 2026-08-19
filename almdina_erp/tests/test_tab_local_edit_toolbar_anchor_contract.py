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


def test_tab_local_toolbar_accepts_native_frappe_section_break_wrapper():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    # Frappe layout fields such as Section Break can expose a native `wrapper`
    # instead of a jQuery `$wrapper`. The tab-local Edit/Save/Cancel toolbar must
    # support both representations or all three toolbar anchors resolve to null.
    assert "field.$wrapper || field.wrapper" in source
    assert "if (wrapper.nodeType) return wrapper" in source
    assert "wrapper[0] && wrapper[0].nodeType" in source


def test_all_three_tab_toolbars_still_use_their_section_break_anchors():
    source = PAGE_EDIT.read_text(encoding="utf-8")

    assert 'anchor: "order_details_section"' in source
    assert 'anchor: "plan_actions_section"' in source
    assert 'anchor: "cost_settings_section"' in source
    assert '["order", "plan", "cost"].forEach((kind) => renderToolbar(frm, kind))' in source
