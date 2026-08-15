from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
RENDER_GUARD = "public/js/door_cutting_order/core/door_cutting_order_save_render_performance_ux.js"
RETIRED_RENDER_GUARD = "public/js/door_cutting_order_save_render_performance_ux.js"
BOARD_TEXT = "public/js/door_cutting_order/order_entry/door_cutting_order_board_text_ux.js"
PLAN_UX = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"


def test_document_render_guard_has_one_core_owner_without_load_order_change():
    assert (ROOT / RENDER_GUARD).exists()
    assert not (ROOT / RETIRED_RENDER_GUARD).exists()

    manifest = runpy.run_path(str(MANIFEST))
    assets = manifest["doctype_js"]["Door Cutting Order"]

    assert assets.count(RENDER_GUARD) == 1
    assert RETIRED_RENDER_GUARD not in assets
    assert assets.index(RENDER_GUARD) == assets.index(BOARD_TEXT) + 1
    assert assets.index(PLAN_UX) == assets.index(RENDER_GUARD) + 1
