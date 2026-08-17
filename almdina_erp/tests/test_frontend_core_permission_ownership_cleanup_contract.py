from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
TAB_PERMISSIONS = "public/js/door_cutting_order/core/door_cutting_order_tab_permissions_ux.js"
PERMISSION_REFRESH = "public/js/door_cutting_order/core/door_cutting_order_permission_refresh_ux.js"
RETIRED_TAB_PERMISSIONS = "public/js/door_cutting_order_tab_permissions_ux.js"
RETIRED_PERMISSION_REFRESH = "public/js/door_cutting_order_permission_refresh_ux.js"
PLAN_SURFACE_BOOTSTRAP = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_surface_bootstrap.js"
DRAWING_PLAN = "public/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js"


def test_core_permission_coordinators_have_one_owner_without_load_order_change():
    for canonical in (TAB_PERMISSIONS, PERMISSION_REFRESH):
        assert (ROOT / canonical).exists()
    for retired in (RETIRED_TAB_PERMISSIONS, RETIRED_PERMISSION_REFRESH):
        assert not (ROOT / retired).exists()

    manifest = runpy.run_path(str(MANIFEST))
    assets = manifest["doctype_js"]["Door Cutting Order"]

    for canonical in (TAB_PERMISSIONS, PERMISSION_REFRESH):
        assert assets.count(canonical) == 1
    for retired in (RETIRED_TAB_PERMISSIONS, RETIRED_PERMISSION_REFRESH):
        assert retired not in assets

    assert assets.index(TAB_PERMISSIONS) == assets.index(PLAN_SURFACE_BOOTSTRAP) + 1
    assert assets.index(PERMISSION_REFRESH) == assets.index(TAB_PERMISSIONS) + 1
    assert assets.index(DRAWING_PLAN) == assets.index(PERMISSION_REFRESH) + 1
