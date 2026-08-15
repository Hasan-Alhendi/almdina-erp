from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "frontend_assets.py"

GEOMETRY = "public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"
OUTPUT_CONTRACT = "public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"
RETIRED_GEOMETRY = "public/js/door_cutting_order_special_shape_geometry.js"
RETIRED_OUTPUT_CONTRACT = "public/js/door_cutting_order_shape_output_contract.js"
GLOBAL_GEOMETRY = "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"
GLOBAL_OUTPUT_CONTRACT = "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"
RETIRED_GLOBAL_GEOMETRY = "/assets/almdina_erp/js/door_cutting_order_special_shape_geometry.js"
RETIRED_GLOBAL_OUTPUT_CONTRACT = "/assets/almdina_erp/js/door_cutting_order_shape_output_contract.js"
PERMISSION_CONTEXT = "public/js/permission_context.js"
PRINT_IDENTITY = "public/js/door_cutting_order/printing/door_cutting_order_print_identity.js"
INPUT_STABILITY = "/assets/almdina_erp/js/input_stability.js"
SECURE_DXF = "/assets/almdina_erp/js/door_cutting_order/cutting_plan/secure_dxf_export.js"


def test_drawing_primitives_keep_existing_entry_contexts_and_load_order():
    assert (ROOT / GEOMETRY).exists()
    assert (ROOT / OUTPUT_CONTRACT).exists()
    assert not (ROOT / RETIRED_GEOMETRY).exists()
    assert not (ROOT / RETIRED_OUTPUT_CONTRACT).exists()

    manifest = runpy.run_path(str(MANIFEST))
    global_assets = manifest["app_include_js"]
    form_assets = manifest["doctype_js"]["Door Cutting Order"]

    assert global_assets.count(GLOBAL_GEOMETRY) == 1
    assert global_assets.count(GLOBAL_OUTPUT_CONTRACT) == 1
    assert RETIRED_GLOBAL_GEOMETRY not in global_assets
    assert RETIRED_GLOBAL_OUTPUT_CONTRACT not in global_assets
    assert global_assets.index(GLOBAL_GEOMETRY) == global_assets.index(INPUT_STABILITY) + 1
    assert global_assets.index(GLOBAL_OUTPUT_CONTRACT) == global_assets.index(GLOBAL_GEOMETRY) + 1
    assert global_assets.index(SECURE_DXF) == global_assets.index(GLOBAL_OUTPUT_CONTRACT) + 1

    assert form_assets.count(GEOMETRY) == 1
    assert form_assets.count(OUTPUT_CONTRACT) == 1
    assert RETIRED_GEOMETRY not in form_assets
    assert RETIRED_OUTPUT_CONTRACT not in form_assets
    assert form_assets.index(GEOMETRY) == form_assets.index(PERMISSION_CONTEXT) + 1
    assert form_assets.index(OUTPUT_CONTRACT) == form_assets.index(GEOMETRY) + 1
    assert form_assets.index(PRINT_IDENTITY) == form_assets.index(OUTPUT_CONTRACT) + 1
