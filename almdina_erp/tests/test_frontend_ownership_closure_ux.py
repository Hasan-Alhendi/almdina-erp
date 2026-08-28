from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"
PUBLIC_JS = ROOT / "public" / "js"
REGISTRY = (
    PUBLIC_JS
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_workspace_asset_registry.js"
)


def _normalize_global_asset(path: str) -> str:
    prefix = "/assets/almdina_erp/js/"
    assert path.startswith(prefix)
    return path.removeprefix(prefix)


def _normalize_doctype_asset(path: str) -> str:
    prefix = "public/js/"
    assert path.startswith(prefix)
    return path.removeprefix(prefix)


def test_door_cutting_order_dual_loads_are_an_explicit_small_allowlist():
    manifest = runpy.run_path(str(MANIFEST))
    global_assets = {_normalize_global_asset(path) for path in manifest["app_include_js"]}
    order_assets = {
        _normalize_doctype_asset(path)
        for path in manifest["doctype_js"]["Door Cutting Order"]
    }

    # P2 removes heavy Plan modules from both global and form-eager ownership.
    # Only the two established shared bootstrap compatibility assets remain dual.
    assert global_assets & order_assets == {
        "permission_context.js",
        "input_stability.js",
    }

    registry = REGISTRY.read_text(encoding="utf-8")
    for lazy_plan_asset in (
        "door_cutting_order/cutting_plan/secure_dxf_export.js",
        "door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js",
    ):
        assert lazy_plan_asset not in global_assets
        assert lazy_plan_asset not in order_assets
        assert Path(lazy_plan_asset).name in registry


def test_global_drawing_primitives_are_not_re_evaluated_by_doctype_js():
    manifest = runpy.run_path(str(MANIFEST))
    global_assets = {_normalize_global_asset(path) for path in manifest["app_include_js"]}
    order_assets = {
        _normalize_doctype_asset(path)
        for path in manifest["doctype_js"]["Door Cutting Order"]
    }
    primitives = {
        "door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
        "door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
    }

    assert primitives <= global_assets
    assert primitives.isdisjoint(order_assets)


def test_lazy_feature_reload_guards_remain_idempotent():
    secure_dxf = (
        PUBLIC_JS
        / "door_cutting_order"
        / "cutting_plan"
        / "secure_dxf_export.js"
    ).read_text(encoding="utf-8")
    drawing_plan = (
        PUBLIC_JS
        / "door_cutting_order"
        / "cutting_plan"
        / "door_cutting_order_drawing_plan_ux.js"
    ).read_text(encoding="utf-8")

    assert "if (window.__almdinaSecureDxfExportLoaded) return;" in secure_dxf
    assert "window.__almdinaSecureDxfExportLoaded = true;" in secure_dxf
    assert "if (window.AlmdinaDrawingPlanUX) return;" in drawing_plan


def test_retired_root_order_entry_points_do_not_return():
    retired = {
        "door_cutting_order_clipped_corner_ux.js",
        "door_cutting_order_list.js",
        "door_cutting_order_text_board_plan_ux.js",
        "door_cutting_order_fast_save_ux.js",
        "door_cutting_order_tab_permissions_ux.js",
        "door_cutting_order_permission_refresh_ux.js",
        "door_cutting_order_save_render_performance_ux.js",
        "door_cutting_order_special_shape_geometry.js",
        "door_cutting_order_shape_output_contract.js",
    }

    assert retired.isdisjoint({path.name for path in PUBLIC_JS.glob("door_cutting_order_*.js")})