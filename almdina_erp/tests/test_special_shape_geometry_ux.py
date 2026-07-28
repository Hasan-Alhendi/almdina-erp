from __future__ import annotations

import json
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.strategies.maxrects import pack_maxrects


ROOT = Path(__file__).resolve().parents[1]
DETAIL = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order_detail"
    / "door_cutting_order_detail.json"
)
PLACED = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "cutting_plan_piece"
    / "cutting_plan_piece.json"
)
ORDER = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"
ORDER_JS = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.js"
SERVICE = ROOT / "almdina_erp" / "services" / "special_shape_service.py"
PLAN = ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
REMNANTS = ROOT / "almdina_erp" / "services" / "remnant_planning.py"
EXPORT = ROOT / "almdina_erp" / "services" / "export_validation_service.py"
GEOMETRY = ROOT / "public" / "js" / "door_cutting_order_special_shape_geometry.js"
BUILDER = ROOT / "public" / "js" / "door_cutting_order_special_shape_builder_ux.js"
WORKFLOW = ROOT / "public" / "js" / "door_cutting_order_workflow.js"
SECURE_DXF = ROOT / "public" / "js" / "secure_dxf_export.js"
HOOKS = ROOT / "hooks.py"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_exact_geometry_is_separate_from_legacy_documentation_and_persisted_in_plan():
    detail = _fields(DETAIL)
    placed = _fields(PLACED)

    assert detail["special_shape_drawing_json"]["fieldtype"] == "Long Text"
    assert detail["special_shape_geometry_json"]["fieldtype"] == "Long Text"
    assert detail["special_shape_geometry_json"]["hidden"] == 1
    assert placed["special_shape_geometry_json"]["fieldtype"] == "Long Text"
    assert placed["special_shape_geometry_json"]["read_only"] == 1


def test_geometry_module_stays_available_but_classic_editor_remains_primary():
    hooks = HOOKS.read_text(encoding="utf-8")
    geometry_hook = '"public/js/door_cutting_order_special_shape_geometry.js"'
    operator_hook = '"public/js/door_cutting_order_operator_ux.js"'
    legacy_hook = '"public/js/door_cutting_order_special_shape_ux.js"'
    builder_hook = '"public/js/door_cutting_order_special_shape_builder_ux.js"'

    assert geometry_hook in hooks
    assert legacy_hook in hooks
    assert builder_hook not in hooks
    assert hooks.index(geometry_hook) < hooks.index(operator_hook)
    assert hooks.index(operator_hook) < hooks.index(legacy_hook)

    legacy = (ROOT / "public" / "js" / "door_cutting_order_special_shape_ux.js").read_text(
        encoding="utf-8"
    )
    assert "window.AlmdinaSpecialShapeEditor = {" in legacy
    assert "رسم الدرفة الخاصة رقم" in legacy


def test_builder_is_dimension_driven_and_has_practical_polygon_controls():
    builder = BUILDER.read_text(encoding="utf-8")
    geometry = GEOMETRY.read_text(encoding="utf-8")

    for template in (
        "single-slope",
        "double-clipped",
        "trapezoid",
        "l-notch",
        "arch",
        "custom",
    ):
        assert template in builder
        assert template in geometry

    assert 'data-point-axis="x"' in builder
    assert 'data-point-axis="y"' in builder
    assert "data-edge-index" in builder
    assert "dco-delete-point" in builder
    assert "dco-shape-undo" in builder
    assert "dco-shape-redo" in builder
    assert "جاهز للقص" in builder
    assert "geometry.validate" in builder
    assert "special_shape_geometry_json = geometry.serialize(payload)" in builder


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
    expanded = expand_piece_groups(
        [
            {
                "width_cm": 60,
                "length_cm": 80,
                "qty": 1,
                "piece_type": "Special",
                "special_shape_geometry_json": geometry_json,
            }
        ]
    )
    assert expanded[0]["special_shape_geometry_json"] == geometry_json

    packed = pack_maxrects(expanded, 122, 244, 0.3, "best_short_side")
    placed = packed["sheets"][0]["pieces"][0]
    assert placed["special_shape_geometry_json"] == geometry_json

    for path in (PLAN, REMNANTS, EXPORT):
        source = path.read_text(encoding="utf-8")
        assert "special_shape_geometry_json" in source, path


def test_plan_print_and_all_dxf_paths_use_exact_special_polygon_when_available():
    order_js = ORDER_JS.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    secure_dxf = SECURE_DXF.read_text(encoding="utf-8")

    for source in (order_js, workflow, secure_dxf):
        assert "AlmdinaSpecialShapeGeometry" in source
        assert "isExact(piece)" in source
        assert "dxfPoints(piece" in source

    assert "dco-special-exact-piece" in order_js
    assert "◆ درفة خاصة · مسار هندسي" in order_js
    assert "dco-special-exact-piece" in workflow
