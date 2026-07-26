from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DETAIL_JSON = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order_detail"
    / "door_cutting_order_detail.json"
)
PLAN_PIECE_JSON = (
    APP_ROOT
    / "almdina_erp"
    / "doctype"
    / "cutting_plan_piece"
    / "cutting_plan_piece.json"
)
ORDER_PY = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"
ORDER_JS = APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.js"
ENGINE = APP_ROOT / "almdina_erp" / "services" / "cutting_engine.py"
PLAN_SERVICE = APP_ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
EXPORT_SERVICE = APP_ROOT / "almdina_erp" / "services" / "export_validation_service.py"
OPERATOR = APP_ROOT / "public" / "js" / "door_cutting_order_operator_ux.js"
CORNER_UX = APP_ROOT / "public" / "js" / "door_cutting_order_clipped_corner_ux.js"
SECURE_DXF = APP_ROOT / "public" / "js" / "secure_dxf_export.js"
HOOKS = APP_ROOT / "hooks.py"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_measurement_and_immutable_plan_schemas_store_clipped_corner_geometry():
    detail = _fields(DETAIL_JSON)
    placed = _fields(PLAN_PIECE_JSON)
    assert detail["piece_type"]["options"] == "Regular\nClipped Corner\nSpecial"
    assert placed["piece_type"]["options"] == "Regular\nClipped Corner\nSpecial"

    for fields in (detail, placed):
        assert fields["clipped_corner_position"]["options"] == (
            "Top Right\nTop Left\nBottom Right\nBottom Left"
        )
        assert fields["clipped_corner_width_cm"]["fieldtype"] == "Float"
        assert fields["clipped_corner_length_cm"]["fieldtype"] == "Float"


def test_server_validates_defaults_and_carries_geometry_through_every_plan_snapshot():
    order = ORDER_PY.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    plan_service = PLAN_SERVICE.read_text(encoding="utf-8")
    export_service = EXPORT_SERVICE.read_text(encoding="utf-8")

    assert 'PIECE_TYPES = {"Regular", "Clipped Corner", "Special"}' in order
    assert "CLIPPED_CORNER_POSITIONS" in order
    assert "Clipped Corner Width must be smaller than the piece width" in order
    assert '"clipped_corner_position": row.clipped_corner_position or ""' in order

    for source in (engine, plan_service, export_service):
        assert "clipped_corner_position" in source
        assert "clipped_corner_width_cm" in source
        assert "clipped_corner_length_cm" in source
    assert "doc._validate_special_shape_rows()" in export_service
    assert "doc._calculate_cutting_plan(settings, input_fingerprint)" in export_service


def test_fast_measurements_offer_one_click_corner_settings_with_live_visual_preview():
    operator = OPERATOR.read_text(encoding="utf-8")
    editor = CORNER_UX.read_text(encoding="utf-8")
    hooks = HOOKS.read_text(encoding="utf-8")

    assert '<option value="Clipped Corner"' in operator
    assert "AlmdinaClippedCornerEditor.open(frm, row)" in operator
    assert "dco-clipped-corner-row" in operator
    assert "dco-corner-position-grid" in editor
    assert "data-corner-preview" in editor
    assert "جعل المسافتين متساويتين" in editor
    assert "المستطيل الخارجي هو المساحة المحجوزة الآمنة" in editor
    assert hooks.index("door_cutting_order_clipped_corner_ux.js") < hooks.index(
        "door_cutting_order_operator_ux.js"
    )


def test_cutting_plan_and_dxf_use_the_same_five_sided_geometry():
    order_js = ORDER_JS.read_text(encoding="utf-8")
    secure_dxf = SECURE_DXF.read_text(encoding="utf-8")
    editor = CORNER_UX.read_text(encoding="utf-8")

    assert "AlmdinaClippedCornerGeometry.pointsAttribute(piece, 100, 100)" in order_js
    assert "dco-clipped-corner-piece" in order_js
    assert "⌑ زاوية مقصوصة" in order_js
    assert "closedPath(\"CUT_PATH\", geometry.dxfPoints" in secure_dxf
    assert "ROTATED_POSITION" in editor
    assert "dxfPoints" in editor
