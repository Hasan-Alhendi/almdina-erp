from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DCO_JS = APP_ROOT / "public" / "js" / "door_cutting_order"
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
POLICY = APP_ROOT / "almdina_erp" / "domain" / "orders" / "piece_policy.py"
ADAPTER = (
    APP_ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "piece_policy_adapter.py"
)
PLAN_ADAPTER = APP_ROOT / "almdina_erp" / "infrastructure" / "frappe" / "orders" / "plan_adapter.py"
PRIMITIVES = APP_ROOT / "almdina_erp" / "domain" / "cutting" / "primitives.py"
EXPORT_SERVICE = APP_ROOT / "almdina_erp" / "services" / "export_validation_service.py"
OPERATOR = DCO_JS / "order_entry" / "door_cutting_order_operator_ux.js"
EXTRA_ADDONS = (
    DCO_JS / "order_entry" / "extra_addons" / "door_cutting_order_extra_addons_ux.js"
)
CORNER_UX = DCO_JS / "drawing" / "door_cutting_order_clipped_corner_ux.js"
PLAN_RENDERER = DCO_JS / "cutting_plan" / "door_cutting_order_cutting_plan_renderer.js"
PIECE_GEOMETRY = DCO_JS / "cutting_plan" / "door_cutting_order_piece_geometry.js"
SECURE_DXF = DCO_JS / "cutting_plan" / "secure_dxf_export.js"
ASSETS = APP_ROOT / "frontend_assets.py"

PIECE_TYPE_OPTIONS = "Regular\nClipped Corner\nL-Shaped Corner\nSpecial\nExtra"


def _fields(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {field["fieldname"]: field for field in payload["fields"]}


def test_measurement_and_immutable_plan_schemas_store_clipped_corner_geometry():
    detail = _fields(DETAIL_JSON)
    placed = _fields(PLAN_PIECE_JSON)
    assert detail["piece_type"]["options"] == PIECE_TYPE_OPTIONS
    assert placed["piece_type"]["options"] == PIECE_TYPE_OPTIONS

    for fields in (detail, placed):
        assert fields["clipped_corner_position"]["options"] == (
            "Top Right\nTop Left\nBottom Right\nBottom Left"
        )
        assert fields["clipped_corner_width_cm"]["fieldtype"] == "Float"
        assert fields["clipped_corner_length_cm"]["fieldtype"] == "Float"


def test_server_validates_defaults_and_carries_geometry_through_every_plan_snapshot():
    policy = POLICY.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    plan_adapter = PLAN_ADAPTER.read_text(encoding="utf-8")
    primitives = PRIMITIVES.read_text(encoding="utf-8")
    export_service = EXPORT_SERVICE.read_text(encoding="utf-8")

    assert "L-Shaped Corner" in policy
    assert "def is_corner_cut" in policy
    assert "is_corner_cut(row.piece_type)" in adapter
    assert "Clipped Corner Width must be smaller than the piece" in adapter
    assert "width." in adapter
    assert '"clipped_corner_position": row.clipped_corner_position or ""' in plan_adapter

    for source in (plan_adapter, primitives, export_service):
        assert "clipped_corner_position" in source
        assert "clipped_corner_width_cm" in source
        assert "clipped_corner_length_cm" in source
    assert "doc._validate_special_shape_rows()" in export_service
    assert "doc._calculate_cutting_plan(settings, input_fingerprint)" in export_service


def test_fast_measurements_offer_one_click_corner_settings_with_live_visual_preview():
    operator = OPERATOR.read_text(encoding="utf-8")
    extra_addons = EXTRA_ADDONS.read_text(encoding="utf-8")
    editor = CORNER_UX.read_text(encoding="utf-8")
    assets = ASSETS.read_text(encoding="utf-8")

    assert '<option value="Clipped Corner"' in operator
    assert '<option value="L-Shaped Corner"' in operator
    assert 'value: "L-Shaped Corner"' in extra_addons
    assert "AlmdinaClippedCornerEditor.open(currentFrm, row)" in operator
    assert "if (!row || !requirePieceDimensions(row, tr)) return" in operator
    assert "isCornerCut" in operator
    assert "dco-clipped-corner-row" in operator
    assert "dco-corner-position-grid" in editor
    assert "data-corner-preview" in editor
    assert "جعل المسافتين متساويتين" in editor
    assert "المستطيل الخارجي هو المساحة المحجوزة الآمنة" in editor
    assert "let activeDialog = null" in editor
    assert "Prevent stacked corner dialogs" in editor
    open_fn = editor.split("function open(frm, row, options = {}) {", 1)[1]
    open_fn = open_fn.split("function view(frm, row)", 1)[0]
    assert "if (!dimensions.width || !dimensions.length)" in open_fn
    assert open_fn.index("if (!dimensions.width || !dimensions.length)") < open_fn.index(
        "installStyles()"
    )
    assert open_fn.index("if (!dimensions.width || !dimensions.length)") < open_fn.index(
        "new frappe.ui.Dialog"
    )
    assert "أدخل عرض الدرفة وطولها أولًا، ثم افتح إعداد الزاوية." in open_fn
    assert 'const L_TYPE = "L-Shaped Corner"' in editor
    assert "cutStyle" in editor
    assert assets.index("door_cutting_order_clipped_corner_ux.js") < assets.index(
        "door_cutting_order_operator_ux.js"
    )


def test_cutting_plan_and_dxf_use_the_same_shared_corner_geometry():
    order_js = PLAN_RENDERER.read_text(encoding="utf-8")
    piece_geometry = PIECE_GEOMETRY.read_text(encoding="utf-8")
    secure_dxf = SECURE_DXF.read_text(encoding="utf-8")
    editor = CORNER_UX.read_text(encoding="utf-8")

    assert "window.AlmdinaClippedCornerGeometry" in piece_geometry
    assert "corner.points(piece, widthMm, heightMm)" in piece_geometry
    assert "AlmdinaCuttingPlanPieceGeometry" in order_js
    assert "dco-clipped-corner-piece" in order_js
    assert "isCornerCut" in order_js
    assert "typeLabel(piece)" in order_js
    assert "clippedGeometry && clippedGeometry.isCornerCut(piece)" in secure_dxf
    assert "dxfPoints" in editor
    assert "ROTATED_POSITION" in editor
    assert '"L"' in editor
