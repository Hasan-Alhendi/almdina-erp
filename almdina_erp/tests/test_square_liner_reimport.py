"""Re-import of an unmodified Linear DXF for a square door.

Order 26-00105 exported a 50×50 cm door with the liner on the right, 10 cm
from the edge, 18 mm wide, and a 5 mm bit. The uploaded plan revision still
stored the 3 mm default, so the toolpath extension of 2.5 mm was measured
against a 1.5 mm radius and rejected as liner_shape_mismatch / extension_short
(expected 0.150 cm). Equal width and height must not invent a 90° turn.
"""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.almdina_erp.domain.cutting.catalog import DEFAULT_OPTIMIZATION_MODE_ID
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    OUTER_SIDES,
    LinerPiece,
    liner_toolpath_mm,
    transform_point,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import DRAFT, SYSTEM
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    DEFAULT_MACHINE_TYPE,
    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_runtime_repository as runtime
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError
from almdina_erp.almdina_erp.services.strict_dxf_import_service import parse_production_dxf

ROOT = Path(__file__).resolve().parents[1]
FULL_HEIGHT_MM = 2440.0
TRIM_MM = 5.0


def _settings(kerf_mm: float):
    return normalize_plan_settings(
        optimization_mode=DEFAULT_OPTIMIZATION_MODE_ID,
        machine_type=DEFAULT_MACHINE_TYPE,
        optimization_time_limit_sec=DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
        kerf_mm=kerf_mm,
        preferred_trim_mm=TRIM_MM,
    )


def _order(
    *,
    width_cm: float,
    length_cm: float,
    side: str,
    allow_rotation: int = 0,
    offset_cm: float = 10,
    width_liner_cm: float = 1.8,
    liner_start_cm: float = 0,
    liner_length_cm: float = 0,
    piece_type: str = "Regular",
):
    return SimpleNamespace(
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        default_edge_type="",
        pieces=[
            SimpleNamespace(
                piece_instance_id="piece-1",
                qty=1,
                piece_type=piece_type,
                width_cm=width_cm,
                length_cm=length_cm,
                cut_width_cm=width_cm,
                cut_length_cm=length_cm,
                allow_rotation=allow_rotation,
                extra_liner=1,
                extra_back_groove=0,
                extra_full_door_double=0,
                extra_recessed_handle_cutout=0,
                extra_double=0,
                liner_reference_side=side,
                liner_offset_cm=offset_cm,
                liner_width_cm=width_liner_cm,
                liner_start_cm=liner_start_cm,
                liner_length_cm=liner_length_cm,
                edge_long_right=0,
                edge_long_left=0,
                edge_width_top=0,
                edge_width_bottom=0,
                edge_break=0,
            )
        ],
    )


def _sheet_point(point, origin=(0.0, 0.0)):
    origin_x, origin_y = origin
    x, y = point
    return (
        TRIM_MM + origin_x + x,
        FULL_HEIGHT_MM - TRIM_MM - (origin_y + y),
    )


def _write_plan(outline, liner, *, label="1"):
    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    for layer_name in ("SHEET_OUTLINE", "CUT_PATH", "Liner", "text"):
        if layer_name not in document.layers:
            document.layers.add(name=layer_name)
    sheet = ((0, 0), (1220, 0), (1220, 2440), (0, 2440))
    for start, end in zip(sheet, (*sheet[1:], sheet[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "SHEET_OUTLINE"})
    for start, end in zip(outline, (*outline[1:], outline[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
    modelspace.add_lwpolyline(liner, dxfattribs={"layer": "Liner"}, close=False)
    modelspace.add_text(label, dxfattribs={"layer": "text", "insert": outline[0], "height": 12})
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    document.saveas(handle.name)
    return handle.name


def _normalize(path: str) -> str:
    normalized = rebuild_autocad_dxf(Path(path).read_bytes())
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    Path(handle.name).write_bytes(normalized)
    return handle.name


def _import(path: str, order, *, kerf_mm: float):
    with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
        return parse_production_dxf(path, order, settings=_settings(kerf_mm))


def _placed_toolpath(piece, side, *, turns=0, origin=(0.0, 0.0), start_cm=0, length_cm=0):
    width_mm = piece.width_cm * 10.0
    height_mm = piece.length_cm * 10.0
    outline = ((0.0, 0.0), (width_mm, 0.0), (width_mm, height_mm), (0.0, height_mm))
    liner = liner_toolpath_mm(piece, side, 10, 1.8, 5, start_cm, length_cm)
    if turns:
        outline = tuple(
            transform_point(point, mirrored=False, quarter_turns=turns, width=width_mm, height=height_mm)
            for point in outline
        )
        liner = [
            transform_point(point, mirrored=False, quarter_turns=turns, width=width_mm, height=height_mm)
            for point in liner
        ]
    return (
        tuple(_sheet_point(point, origin) for point in outline),
        [_sheet_point(point, origin) for point in liner],
    )


def test_square_export_normalizes_and_reimports_without_assuming_rotation(tmp_path):
    client_path = tmp_path / "square-client.dxf"
    env = os.environ.copy()
    env["SQUARE_LINER_DXF_OUT"] = str(client_path)
    subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "secure_dxf_topology_export.test.js")],
        check=True,
        env=env,
    )
    raw = client_path.read_text(encoding="ascii").replace("\r\n", "\n")
    assert "10\n402.5\n20\n507.5\n" in raw
    assert "10\n5\n20\n5\n" in raw

    normalized = rebuild_autocad_dxf(client_path.read_bytes())
    result = ezdxf.read(io.StringIO(normalized.decode("utf-8")))
    liner = next(entity for entity in result.modelspace() if entity.dxftype() == "LWPOLYLINE")
    assert liner.closed is False
    assert str(liner.dxf.layer) == "Liner"
    assert result.audit().has_errors is False

    normalized_path = tmp_path / "square-normalized.dxf"
    normalized_path.write_bytes(normalized)
    snapshot = _import(
        str(normalized_path),
        _order(width_cm=50, length_cm=50, side="edge_long_right", allow_rotation=1),
        kerf_mm=5,
    )
    piece = snapshot["sheets"][0]["pieces"][0]
    assert piece["rotated"] is False
    assert piece["w"] == 50
    assert piece["h"] == 50
    assert piece["overlays"][0]["kind"] == "liner"


def test_real_square_file_matches_five_millimetre_bit_and_rejects_three():
    source = _write_plan(
        ((5, 5), (505, 5), (505, 505), (5, 505)),
        [
            (402.5, 507.5),
            (402.5, 2.5),
            (397.5, 2.5),
            (397.5, 507.5),
            (394.5, 507.5),
            (394.5, 2.5),
            (389.5, 2.5),
            (389.5, 507.5),
        ],
    )
    normalized = _normalize(source)
    order = _order(width_cm=50, length_cm=50, side="edge_long_right", allow_rotation=1)
    snapshot = _import(normalized, order, kerf_mm=5)
    assert snapshot["sheets"][0]["pieces"][0]["rotated"] is False

    try:
        _import(normalized, order, kerf_mm=3)
    except DxfImportError as error:
        issue = error.issues[0]
        assert issue.code == "LINER_SHAPE_MISMATCH"
        assert issue.params["reason_code"] == "extension_short"
        assert issue.params["expected"] == "0.150"
    else:
        raise AssertionError("a 5 mm toolpath must not pass a 3 mm bit check")


def test_square_liner_on_the_wrong_side_is_rejected():
    piece = LinerPiece("Regular", 50, 50)
    outline, liner = _placed_toolpath(piece, "edge_long_left")
    path = _normalize(_write_plan(outline, liner))
    try:
        _import(
            path,
            _order(width_cm=50, length_cm=50, side="edge_long_right"),
            kerf_mm=5,
        )
    except DxfImportError as error:
        assert error.issues[0].code == "LINER_SIDE_MISMATCH"
    else:
        raise AssertionError("a left liner must not satisfy a right-side order")


def test_each_square_side_reimports():
    piece = LinerPiece("Regular", 50, 50)
    for side in OUTER_SIDES:
        outline, liner = _placed_toolpath(piece, side)
        snapshot = _import(
            _normalize(_write_plan(outline, liner)),
            _order(width_cm=50, length_cm=50, side=side, allow_rotation=1),
            kerf_mm=5,
        )
        assert snapshot["sheets"][0]["pieces"][0]["rotated"] is False


def test_rectangle_reimports_unrotated_and_after_a_quarter_turn():
    piece = LinerPiece("Regular", 40, 60)
    outline, liner = _placed_toolpath(piece, "edge_long_right")
    snapshot = _import(
        _normalize(_write_plan(outline, liner)),
        _order(width_cm=40, length_cm=60, side="edge_long_right", allow_rotation=1),
        kerf_mm=5,
    )
    assert snapshot["sheets"][0]["pieces"][0]["rotated"] is False

    outline, liner = _placed_toolpath(piece, "edge_long_right", turns=1)
    snapshot = _import(
        _normalize(_write_plan(outline, liner)),
        _order(width_cm=40, length_cm=60, side="edge_long_right", allow_rotation=1),
        kerf_mm=5,
    )
    assert snapshot["sheets"][0]["pieces"][0]["rotated"] is True


def test_partial_export_normalizes_and_reimports():
    piece = LinerPiece("Regular", 50, 50)
    outline, liner = _placed_toolpath(piece, "edge_long_right", start_cm=10, length_cm=30)
    path = _normalize(_write_plan(outline, liner))
    order = _order(
        width_cm=50,
        length_cm=50,
        side="edge_long_right",
        liner_start_cm=10,
        liner_length_cm=30,
    )
    snapshot = _import(path, order, kerf_mm=5)
    assert snapshot["sheets"][0]["pieces"][0]["overlays"][0]["kind"] == "liner"
    try:
        _import(path, _order(width_cm=50, length_cm=50, side="edge_long_right", liner_start_cm=10, liner_length_cm=20), kerf_mm=5)
    except DxfImportError as error:
        assert error.issues[0].code == "LINER_SHAPE_MISMATCH"
    else:
        raise AssertionError("a shorter ordered length must reject the longer toolpath")


def test_upload_settings_follow_the_system_draft_not_a_stale_uploaded_revision(monkeypatch):
    system = SimpleNamespace(name="CP-SYSTEM", kerf_mm=5)
    uploaded = SimpleNamespace(name="CP-UPLOADED", kerf_mm=3)

    def latest(_order_name, **filters):
        if filters.get("source_type") == SYSTEM and filters.get("status") == DRAFT:
            return system
        return uploaded

    monkeypatch.setattr(runtime, "latest_plan", latest)
    monkeypatch.setattr(runtime, "plan_settings", lambda plan: SimpleNamespace(kerf_mm=plan.kerf_mm))
    assert runtime.manufacturing_plan_settings("26-00105").kerf_mm == 5

    monkeypatch.setattr(runtime, "latest_plan", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runtime,
        "seed_plan_settings",
        lambda _order_name: SimpleNamespace(kerf_mm=3),
    )
    assert runtime.manufacturing_plan_settings("26-00105").kerf_mm == 3
