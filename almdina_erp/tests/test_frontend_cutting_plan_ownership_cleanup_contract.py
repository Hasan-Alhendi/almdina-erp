from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
CANONICAL = "public/js/door_cutting_order/cutting_plan/door_cutting_order_text_board_plan_ux.js"
RETIRED_ROOT = "public/js/door_cutting_order_text_board_plan_ux.js"
PLAN_UX = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"
FAST_SAVE = "public/js/door_cutting_order_fast_save_ux.js"


def test_text_board_plan_has_one_cutting_plan_owner_without_load_order_change():
    assert (ROOT / CANONICAL).exists()
    assert not (ROOT / RETIRED_ROOT).exists()

    manifest = runpy.run_path(str(MANIFEST))
    assets = manifest["doctype_js"]["Door Cutting Order"]

    assert assets.count(CANONICAL) == 1
    assert RETIRED_ROOT not in assets
    assert assets.index(CANONICAL) == assets.index(PLAN_UX) + 1
    assert assets.index(FAST_SAVE) == assets.index(CANONICAL) + 1
