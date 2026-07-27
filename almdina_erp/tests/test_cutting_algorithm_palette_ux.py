from __future__ import annotations

import json
import re
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DOCTYPE_JSON = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
PALETTE_UX = APP_ROOT / "public" / "js" / "door_cutting_order_algorithm_palette_ux.js"
PLAN_UX = APP_ROOT / "public" / "js" / "door_cutting_order_plan_ux.js"
HOOKS = APP_ROOT / "hooks.py"


def test_algorithm_palette_matches_packing_mode_options_and_keeps_current_recalculate_action():
    payload = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
    packing_field = next(field for field in payload["fields"] if field.get("fieldname") == "packing_mode")
    expected_modes = {mode for mode in packing_field["options"].splitlines() if mode}

    palette = PALETTE_UX.read_text(encoding="utf-8")
    plan_ux = PLAN_UX.read_text(encoding="utf-8")
    hooks = HOOKS.read_text(encoding="utf-8")
    palette_modes = set(re.findall(r'\{ value: "([^"]+)"', palette))

    assert palette_modes == expected_modes
    assert '"public/js/door_cutting_order_algorithm_palette_ux.js"' in hooks
    assert hooks.index('"public/js/door_cutting_order_plan_ux.js"') < hooks.index(
        '"public/js/door_cutting_order_algorithm_palette_ux.js"'
    )
    assert "dco-algorithm-search" in palette
    assert 'await frm.set_value("packing_mode", mode)' in palette
    assert '$recalculate.trigger("click")' in palette
    assert "إعادة الحساب بالإعدادات الحالية" in plan_ux
