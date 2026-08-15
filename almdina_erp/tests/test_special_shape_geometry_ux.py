from __future__ import annotations

import json
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.strategies.maxrects import pack_maxrects


ROOT = Path(__file__).resolve().parents[1]
DETAIL = ROOT / "almdina_erp" / "doctype" / "door_cutting_order_detail" / "door_cutting_order_detail.json"
PLACED = ROOT / "almdina_erp" / "doctype" / "cutting_plan_piece" / "cutting_plan_piece.json"
ORDER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
PLAN_RENDERER = CUTTING_PLAN / "door_cutting_order_cutting_plan_renderer.js"
SERVICE = ROOT / "almdina_erp" / "services" / "special_shape_service.py"
PLAN = ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
REMNANTS = ROOT / "almdina_erp" / "services" / "remnant_planning.py"
EXPORT = ROOT / "almdina_erp" / "services" / "export_validation_service.py"
GEOMETRY = ROOT / "public" / "js" / "door_cutting_order_special_shape_geometry.js"
SECURE_DXF = CUTTING_PLAN / "secure_dxf_export.js"
HOOKS = ROOT / "hooks.py"
EDITOR = ROOT / "public" / "js" / "door_cutting_order" / "drawing" / "special_shape_facade.js"
V3_GEOMETRY = ROOT / "public" / "js" / "door_drawing_v3" / "domain" / "geometry.js"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_exact_geometry_is_separate_from_documentation_and_persisted_in_plan():
    detail = _fields(DETAIL)
    placed = _fields(PLACED)
    assert detail["special_shape_drawing_json"]["fieldtype"] == "Long Text"
    assert detail["special_shape_geometry_json"]["fieldtype"] == "Long Text"
    assert detail["special_shape_geometry_json"]["hidden"] == 1
    assert placed["special_shape_geometry_json"]["fieldtype"] == "Long Text"
    assert placed["special_shape_geometry_json"]["read_only"] == 1


def test_v3_editor_is_primary_while_production_geometry_contract_remains_available():
    hooks = HOOKS.read_text(encoding="utf-8")
    geometry_hook = '"/assets/almdina_erp/js/door_cutting_order_special_shape_geometry.js"'
    contract_hook = '"/assets/almdina_erp/js/door_cutting_order_shape_output_contract.js"'
    editor_hook = '"public/js/door_cutting_order/drawing/special_shape_facade.js"'
    assert geometry_hook in hooks
    assert contract_hook in hooks
    assert editor_hook in hooks
    assert hooks.index(geometry_hook) < hooks.index(contract_hook)

    editor = EDITOR.read_text(encoding="utf-8")
    v3 = V3_GEOMETRY.read_text(encoding="utf-8")
    assert "__doorDrawingV3: true" in editor
    assert "door_drawing_v3/domain/geometry.js" in editor
    assert 'const UNITS = "cm"' not in v3
    assert "EPSILON_MM" in v3
    assert "function line(" in v3
    assert "special_shape_geometry_json" not in v3


def test_server_rejects_unsafe_or_mismatched_polygons_and_documents_exact_geometry():
    service = SERVICE.read_text(encoding="utf-8")
    order = ORDER.read_text(encoding="utf-8")
    assert "def validate_special_shape_geometry" in service
    assert "MAX_GEOMETRY_VERTICES = 64" in service
    assert "_geometry_has_self_intersection(points)" in service
    assert "_geometry_area(points)" in service
    assert "Special shape geometry must touch all four raw-piece bounds." in service
    assert "Special shape geometry width does not match the piece width." in service
    assert "Special shape geometry length does not match the piece length." in service
    assert "validate_special_shape_geometry(" in order
    assert "old_special_geometry != special_geometry" in order
    assert "if special_geometry or (drawing and drawing.get(\"elements\"))" in order
    assert '"special_shape_geometry_json"' in order


def test_exact_geometry_survives_every_packing_and_approved_export_path():
    geometry_json = '{"version":1,"points":[[0,0],[60,0],[60,80],[0,80]]}'
    expanded = expand_piece_groups([
        {
            "width_cm": 60,
            "length_cm": 80,
            "qty": 1,
            "piece_type": "Special",
            "special_shape_geometry_json": geometry_json,
        }
    ])
    assert expanded[0]["special_shape_geometry_json"] == geometry_json
    packed = pack_maxrects(expanded, 122, 244, 0.3, "best_short_side")
    placed = packed["sheets"][0]["pieces"][0]
    assert placed["special_shape_geometry_json"] == geometry_json
    for path in (PLAN, REMNANTS, EXPORT):
        assert "special_shape_geometry_json" in path.read_text(encoding="utf-8"), path


def test_plan_and_current_dxf_paths_use_exact_special_polygon_when_available():
    plan_renderer = PLAN_RENDERER.read_text(encoding="utf-8")
    secure_dxf = SECURE_DXF.read_text(encoding="utf-8")
    for source in (plan_renderer, secure_dxf):
        assert "AlmdinaShapeOutputContract" in source
        assert "hasExactCutPath(piece)" in source
        assert "AlmdinaSpecialShapeGeometry" not in source
    assert "shapeOutput.dxfPoints(piece" in secure_dxf
    assert "dco-special-exact-piece" in plan_renderer
    assert "◆ درفة خاصة · مسار هندسي" in plan_renderer
    assert not (ROOT / "public" / "js" / "door_cutting_order_workflow.js").exists()
