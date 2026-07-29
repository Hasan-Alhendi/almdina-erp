from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCTYPE = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
HOOKS = ROOT / "hooks.py"
PLAN_UX = ROOT / "public" / "js" / "door_cutting_order_plan_ux.js"
CONTROLS_UX = ROOT / "public" / "js" / "door_cutting_order_plan_controls_ux.js"
REMOVED_PALETTE = ROOT / "public" / "js" / "door_cutting_order_algorithm_palette_ux.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_advanced_algorithms_remain_in_the_primary_packing_mode_select():
    payload = json.loads(source(DOCTYPE))
    packing_mode = next(field for field in payload["fields"] if field.get("fieldname") == "packing_mode")
    options = set(packing_mode["options"].splitlines())
    assert {"Auto Pro", "Deep Search", "Optimal Search"}.issubset(options)


def test_duplicate_algorithm_palette_is_removed_and_simple_controls_load_last():
    hooks = source(HOOKS)
    plan = '"public/js/door_cutting_order_plan_ux.js"'
    text_board = '"public/js/door_cutting_order_text_board_plan_ux.js"'
    fast_save = '"public/js/door_cutting_order_fast_save_ux.js"'
    controls = '"public/js/door_cutting_order_plan_controls_ux.js"'

    assert not REMOVED_PALETTE.exists()
    assert "door_cutting_order_algorithm_palette_ux.js" not in hooks
    assert controls in hooks
    assert hooks.index(plan) < hooks.index(text_board) < hooks.index(fast_save) < hooks.index(controls)


def test_simple_controls_keep_only_current_settings_recalculation_action():
    controls = source(CONTROLS_UX)
    plan = source(PLAN_UX)

    for selector in (".dco-auto-pro-plan", ".dco-deep-plan", ".dco-optimal-plan", ".dco-algorithm-palette"):
        assert selector in controls
    assert "find(DUPLICATED_ACTIONS).remove()" in controls
    assert "إعادة الحساب بالإعدادات الحالية" in controls
    assert "إعادة الحساب بالإعدادات الحالية" in plan


def test_advanced_algorithm_labels_are_applied_inside_the_primary_select():
    controls = source(CONTROLS_UX)
    for value, label in (
        ("Auto Pro", "أفضل توزيع متقدم"),
        ("Deep Search", "بحث معمق"),
        ("Optimal Search", "بحث أمثل"),
    ):
        assert f'{{ value: "{value}", label: "{label}" }}' in controls
    assert 'field.$input' in controls
    assert 'option.text(label)' in controls
