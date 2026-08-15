from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
TEXT_BOARD_PLAN = "public/js/door_cutting_order/cutting_plan/door_cutting_order_text_board_plan_ux.js"
FAST_SAVE = "public/js/door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js"
RETIRED_TEXT_BOARD_PLAN = "public/js/door_cutting_order_text_board_plan_ux.js"
RETIRED_FAST_SAVE = "public/js/door_cutting_order_fast_save_ux.js"
PLAN_UX = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"
PLAN_CONTROLS = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js"


def test_cutting_plan_helpers_have_one_feature_owner_without_load_order_change():
    for canonical in (TEXT_BOARD_PLAN, FAST_SAVE):
        assert (ROOT / canonical).exists()
    for retired in (RETIRED_TEXT_BOARD_PLAN, RETIRED_FAST_SAVE):
        assert not (ROOT / retired).exists()

    manifest = runpy.run_path(str(MANIFEST))
    assets = manifest["doctype_js"]["Door Cutting Order"]

    for canonical in (TEXT_BOARD_PLAN, FAST_SAVE):
        assert assets.count(canonical) == 1
    for retired in (RETIRED_TEXT_BOARD_PLAN, RETIRED_FAST_SAVE):
        assert retired not in assets

    assert assets.index(TEXT_BOARD_PLAN) == assets.index(PLAN_UX) + 1
    assert assets.index(FAST_SAVE) == assets.index(TEXT_BOARD_PLAN) + 1
    assert assets.index(PLAN_CONTROLS) == assets.index(FAST_SAVE) + 1
