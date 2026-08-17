from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUICK_ACTIONS = ROOT / "public" / "js" / "shop_floor_quick_actions.js"
DROPDOWN_CSS = ROOT / "public" / "css" / "shop_floor_worker_dropdown.css"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_worker_handoff_uses_anchored_custom_dropdown_not_native_select():
    quick_actions = source(QUICK_ACTIONS)

    assert 'fieldtype: "HTML"' in quick_actions
    assert 'fieldtype: "Select"' not in quick_actions
    assert "frappe.prompt(" not in quick_actions
    assert "function createWorkerDropdownDialog" in quick_actions
    assert 'aria-haspopup="listbox"' in quick_actions
    assert 'role="listbox"' in quick_actions
    assert 'role="option"' in quick_actions
    assert 'event.key === "ArrowDown"' in quick_actions
    assert 'event.key === "Escape"' in quick_actions
    assert "choices.length === 1 ? choices[0] : null" in quick_actions


def test_worker_dropdown_is_scoped_touch_friendly_and_anchored_to_field():
    css = source(DROPDOWN_CSS)
    quick_actions = source(QUICK_ACTIONS)

    assert "shop_floor_worker_dropdown.css" in quick_actions
    assert ".almdina-worker-dropdown {" in css
    assert "position: relative;" in css
    assert ".almdina-worker-dropdown-menu {" in css
    assert "position: absolute;" in css
    assert "inset-inline: 0;" in css
    assert "max-height: min(280px, 36vh);" in css
    assert "overflow-y: auto;" in css
    assert ".almdina-worker-dropdown.is-drop-up" in css
    assert "min-height: 48px;" in css
    assert "@media (max-width: 600px)" in css
    assert "min-height: 52px;" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
