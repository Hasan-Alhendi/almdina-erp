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
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.almdina_erp.domain.cutting.catalog import DEFAULT_OPTIMIZATION_MODE_ID
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    OUTER_SIDES,
    LinerPiece,
    contour_notch_cm,
    liner_toolpath_mm,
    piece_polygon_mm,
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
from almdina_erp.almdina_erp.services import piece_cut_dimension_service
from almdina_erp.almdina_erp.services import strict_dxf_import_service
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
    liner = next(
        entity for entity in result.modelspace()
        if entity.dxftype() == "LWPOLYLINE" and entity.dxf.layer == "Liner"
    )
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


def _band_loader(names):
    return {
        str(name): {"name": str(name), "thickness_mm": Decimal("1"), "disabled": 0}
        for name in names
    }


def _import_banded(path, order, *, kerf_mm):
    def build(source, **kwargs):
        return piece_cut_dimension_service.build_order_piece_cut_specs(
            source,
            profile_loader=_band_loader,
        )

    with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path), patch.object(
        strict_dxf_import_service,
        "build_order_piece_cut_specs",
        build,
    ):
        return parse_production_dxf(path, order, settings=_settings(kerf_mm))


def _blank_edges():
    return dict(
        edge_long_right=0,
        edge_long_left=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_long_right_type_override="",
        edge_long_left_type_override="",
        edge_width_top_type_override="",
        edge_width_bottom_type_override="",
        edge_type="",
        extra_full_door_double=0,
        extra_back_groove=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
    )


def _door(**kwargs):
    base = dict(
        qty=1,
        allow_rotation=0,
        extra_liner=1,
        liner_start_cm=0,
        liner_length_cm=0,
        piece_instance_id="piece",
        clipped_corner_position="Top Right",
        clipped_corner_width_cm=0,
        clipped_corner_length_cm=0,
        edge_break=0,
        edge_break_only=0,
        **_blank_edges(),
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def _board(pieces, default_edge_type=""):
    return SimpleNamespace(
        name="26-00105",
        pieces=pieces,
        default_edge_type=default_edge_type,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
    )


def _write_sheet(parts):
    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    for layer_name in ("SHEET_OUTLINE", "CUT_PATH", "Liner", "text"):
        if layer_name not in document.layers:
            document.layers.add(name=layer_name)
    sheet = ((0, 0), (1220, 0), (1220, 2440), (0, 2440))
    for start, end in zip(sheet, (*sheet[1:], sheet[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "SHEET_OUTLINE"})
    for part in parts:
        outline = part["outline"]
        for start, end in zip(outline, (*outline[1:], outline[0])):
            modelspace.add_line(start, end, dxfattribs={"layer": "CUT_PATH"})
        modelspace.add_lwpolyline(part["liner"], dxfattribs={"layer": "Liner"}, close=False)
        modelspace.add_text(
            part["label"],
            dxfattribs={"layer": "text", "insert": outline[0], "height": 12},
        )
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    document.saveas(handle.name)
    return handle.name


def _write_geometry_sheet(parts):
    """Write the editable pre-CUT_PATH geometry emitted by a system draft."""
    document = ezdxf.new("R2010")
    modelspace = document.modelspace()
    for layer_name in ("SHEET_OUTLINE", "GEOMETRY", "text"):
        if layer_name not in document.layers:
            document.layers.add(name=layer_name)
    sheet = ((0, 0), (1220, 0), (1220, 2440), (0, 2440))
    for start, end in zip(sheet, (*sheet[1:], sheet[0])):
        modelspace.add_line(start, end, dxfattribs={"layer": "SHEET_OUTLINE"})
    for part in parts:
        outline = part["outline"]
        for start, end in zip(outline, (*outline[1:], outline[0])):
            modelspace.add_line(start, end, dxfattribs={"layer": "GEOMETRY"})
        modelspace.add_text(
            part["label"],
            dxfattribs={"layer": "text", "insert": outline[0], "height": 12},
        )
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    document.saveas(handle.name)
    return handle.name


def _anchored(points):
    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    return [(point[0] - min_x, point[1] - min_y) for point in points]


def _manufacturing_part(piece, side, origin, label, **span):
    outline = list(piece_polygon_mm(piece))
    liner = liner_toolpath_mm(
        piece,
        side,
        span.get("offset_cm", 2),
        span.get("width_cm", 1.5),
        span.get("kerf_mm", 3),
        span.get("start_cm", 0),
        span.get("length_cm", 0),
    )
    if span.get("turns") or span.get("mirrored"):
        width_mm = piece.width_cm * 10.0
        height_mm = piece.length_cm * 10.0
        turns = span.get("turns", 0)
        mirrored = bool(span.get("mirrored"))
        outline = [
            transform_point(
                point,
                mirrored=mirrored,
                quarter_turns=turns,
                width=width_mm,
                height=height_mm,
            )
            for point in outline
        ]
        liner = [
            transform_point(
                point,
                mirrored=mirrored,
                quarter_turns=turns,
                width=width_mm,
                height=height_mm,
            )
            for point in liner
        ]
        shift_x = min(point[0] for point in outline)
        shift_y = min(point[1] for point in outline)
        outline = _anchored(outline)
        liner = [(point[0] - shift_x, point[1] - shift_y) for point in liner]
    return {
        "outline": tuple(_sheet_point(point, origin) for point in outline),
        "liner": [_sheet_point(point, origin) for point in liner],
        "label": label,
    }


def _raw_l(position="Top Right", **overrides):
    notch_width, notch_length = contour_notch_cm(
        piece_type="L-Shaped Corner",
        finished_width_cm=overrides.get("finished_width_cm", 40),
        finished_length_cm=overrides.get("finished_length_cm", 40),
        notch_width_cm=overrides.get("notch_width_cm", 20),
        notch_length_cm=overrides.get("notch_length_cm", 30),
        position=position,
        side_thickness_mm=overrides.get("side_mm", {}),
        edge_break=overrides.get("edge_break", True),
        edge_break_thickness_mm=overrides.get("inner_mm", 1),
    )
    return LinerPiece(
        "L-Shaped Corner",
        overrides.get("cut_width_cm", 40),
        overrides.get("cut_length_cm", 40),
        position,
        notch_width,
        notch_length,
    )


def test_l_notch_and_full_break_round_trip_on_one_sheet():
    regular = LinerPiece("Regular", 50, 50)
    shaped = _raw_l()
    clipped = LinerPiece("Clipped Corner", 84, 63, "Top Right", 54, 23)
    path = _normalize(
        _write_sheet(
            [
                _manufacturing_part(
                    regular,
                    "edge_long_right",
                    (0, 0),
                    "1",
                    offset_cm=10,
                    width_cm=1.8,
                    start_cm=0,
                    length_cm=5,
                ),
                _manufacturing_part(shaped, "edge_break", (503, 0), "2", offset_cm=2, width_cm=1.5),
                _manufacturing_part(
                    clipped,
                    "edge_break",
                    (0, 503),
                    "3",
                    offset_cm=10,
                    width_cm=1.5,
                ),
            ]
        )
    )
    order = _board(
        [
            _door(
                piece_instance_id="p1",
                piece_type="Regular",
                width_cm=50,
                length_cm=50,
                cut_width_cm=50,
                cut_length_cm=50,
                liner_reference_side="edge_long_right",
                liner_offset_cm=10,
                liner_width_cm=1.8,
                liner_length_cm=5,
            ),
            _door(
                piece_instance_id="p2",
                piece_type="L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                cut_width_cm=40,
                cut_length_cm=40,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=30,
                edge_break=1,
                liner_reference_side="edge_break",
                liner_offset_cm=2,
                liner_width_cm=1.5,
            ),
            _door(
                piece_instance_id="p3",
                piece_type="Clipped Corner",
                width_cm=84,
                length_cm=63,
                cut_width_cm=84,
                cut_length_cm=63,
                clipped_corner_width_cm=54,
                clipped_corner_length_cm=23,
                edge_break=1,
                liner_reference_side="edge_break",
                liner_offset_cm=10,
                liner_width_cm=1.5,
            ),
        ],
        default_edge_type="band-1",
    )
    pieces = _import_banded(path, order, kerf_mm=3)["sheets"][0]["pieces"]
    assert [piece["source_piece_no"] for piece in pieces] == [1, 2, 3]
    assert [piece["overlays"][0]["kind"] for piece in pieces] == ["liner", "liner", "liner"]


def test_finished_l_notch_is_still_rejected_by_one_millimetre():
    finished = LinerPiece("L-Shaped Corner", 40, 40, "Top Right", 20, 30)
    path = _normalize(
        _write_sheet(
            [_manufacturing_part(finished, "edge_break", (0, 0), "1", offset_cm=2, width_cm=1.5)]
        )
    )
    order = _board(
        [
            _door(
                piece_instance_id="p2",
                piece_type="L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                cut_width_cm=40,
                cut_length_cm=40,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=30,
                edge_break=1,
                liner_reference_side="edge_break",
                liner_offset_cm=2,
                liner_width_cm=1.5,
            )
        ],
        default_edge_type="band-1",
    )
    try:
        _import_banded(path, order, kerf_mm=3)
    except DxfImportError as error:
        issue = error.issues[0]
        assert issue.code == "L_CORNER_NOTCH_MISMATCH"
        by_axis = {item["axis"]: item for item in issue.params["axes"]}
        assert by_axis["width"]["expected_raw_cm"] == "19.900"
        assert by_axis["width"]["actual_raw_cm"] == "20.000"
        assert by_axis["length"]["expected_raw_cm"] == "9.900"
        assert by_axis["length"]["actual_raw_cm"] == "10.000"
    else:
        raise AssertionError("a finished L notch must not satisfy the raw cut")


def test_l_raw_notch_covers_each_corner_without_a_second_strap_deduction():
    for position in ("Top Right", "Top Left", "Bottom Right", "Bottom Left"):
        shaped = _raw_l(position)
        path = _normalize(
            _write_sheet(
                [_manufacturing_part(shaped, "edge_break", (0, 0), "1", offset_cm=2, width_cm=1.5)]
            )
        )
        order = _board(
            [
                _door(
                    piece_instance_id="p2",
                    piece_type="L-Shaped Corner",
                    width_cm=40,
                    length_cm=40,
                    cut_width_cm=40,
                    cut_length_cm=40,
                    clipped_corner_position=position,
                    clipped_corner_width_cm=20,
                    clipped_corner_length_cm=30,
                    edge_break=1,
                    liner_reference_side="edge_break",
                    liner_offset_cm=2,
                    liner_width_cm=1.5,
                )
            ],
            default_edge_type="band-1",
        )
        piece = _import_banded(path, order, kerf_mm=3)["sheets"][0]["pieces"][0]
        assert piece["overlays"][0]["kind"] == "liner"
        assert float(piece["clipped_corner_width_cm"]) == 20
        assert float(piece["clipped_corner_length_cm"]) == 30

    plain = LinerPiece("L-Shaped Corner", 40, 40, "Top Right", 20, 30)
    bare = _import_banded(
        _normalize(
            _write_sheet(
                [_manufacturing_part(plain, "edge_break", (0, 0), "1", offset_cm=2, width_cm=1.5)]
            )
        ),
        _board(
            [
                _door(
                    piece_instance_id="p2",
                    piece_type="L-Shaped Corner",
                    width_cm=40,
                    length_cm=40,
                    cut_width_cm=40,
                    cut_length_cm=40,
                    clipped_corner_width_cm=20,
                    clipped_corner_length_cm=30,
                    edge_break=0,
                    liner_reference_side="edge_break",
                    liner_offset_cm=2,
                    liner_width_cm=1.5,
                )
            ]
        ),
        kerf_mm=3,
    )
    assert bare["sheets"][0]["pieces"][0]["overlays"][0]["kind"] == "liner"

    one_axis = _raw_l(
        side_mm={"long_right": 1, "long_left": 0, "width_top": 0, "width_bottom": 0},
        cut_width_cm=39.9,
        inner_mm=1,
        edge_break=True,
    )
    imported = _import_banded(
        _normalize(
            _write_sheet(
                [_manufacturing_part(one_axis, "edge_break", (0, 0), "1", offset_cm=2, width_cm=1.5)]
            )
        ),
        _board(
            [
                _door(
                    piece_instance_id="p2",
                    piece_type="L-Shaped Corner",
                    width_cm=40,
                    length_cm=40,
                    cut_width_cm=39.9,
                    cut_length_cm=40,
                    clipped_corner_width_cm=20,
                    clipped_corner_length_cm=30,
                    edge_long_right=1,
                    edge_break=1,
                    liner_reference_side="edge_break",
                    liner_offset_cm=2,
                    liner_width_cm=1.5,
                )
            ],
            default_edge_type="band-1",
        ),
        kerf_mm=3,
    )
    assert imported["sheets"][0]["pieces"][0]["w"] == 39.9

    doubled = LinerPiece("L-Shaped Corner", 39.9, 39.9, "Top Right", 20.1, 30.1)
    try:
        _import_banded(
            _normalize(
                _write_sheet(
                    [
                        _manufacturing_part(
                            doubled, "edge_break", (0, 0), "1", offset_cm=2, width_cm=1.5
                        )
                    ]
                )
            ),
            _board(
                [
                    _door(
                        piece_instance_id="p2",
                        piece_type="L-Shaped Corner",
                        width_cm=40,
                        length_cm=40,
                        cut_width_cm=40,
                        cut_length_cm=40,
                        clipped_corner_width_cm=20,
                        clipped_corner_length_cm=30,
                        edge_break=1,
                        liner_reference_side="edge_break",
                        liner_offset_cm=2,
                        liner_width_cm=1.5,
                    )
                ],
                default_edge_type="band-1",
            ),
            kerf_mm=3,
        )
    except DxfImportError as error:
        assert error.issues[0].code in {"L_CORNER_NOTCH_MISMATCH", "CUT_SIZE_MISMATCH"}
    else:
        raise AssertionError("deducting the inner band from the outer size and the notch must fail")


def test_full_break_liner_reimports_with_strap_partial_span_turn_and_mirror():
    clipped = LinerPiece("Clipped Corner", 84, 63, "Top Right", 54, 23)

    def accept(part, **row):
        order = _board(
            [
                _door(
                    piece_instance_id="p3",
                    piece_type="Clipped Corner",
                    width_cm=84,
                    length_cm=63,
                    cut_width_cm=row.pop("cut_width_cm", 84),
                    cut_length_cm=row.pop("cut_length_cm", 63),
                    clipped_corner_width_cm=54,
                    clipped_corner_length_cm=23,
                    liner_reference_side="edge_break",
                    liner_offset_cm=row.pop("offset_cm", 10),
                    liner_width_cm=1.5,
                    **row,
                )
            ],
            default_edge_type="band-1",
        )
        piece = _import_banded(
            _normalize(_write_sheet([part])),
            order,
            kerf_mm=3,
        )["sheets"][0]["pieces"][0]
        assert piece["overlays"][0]["kind"] == "liner"
        return piece

    accept(
        _manufacturing_part(clipped, "edge_break", (0, 0), "1", offset_cm=10, width_cm=1.5),
        edge_break=1,
    )
    accept(
        _manufacturing_part(clipped, "edge_break", (0, 0), "1", offset_cm=10, width_cm=1.5),
        edge_break=0,
    )
    accept(
        _manufacturing_part(
            clipped,
            "edge_break",
            (0, 0),
            "1",
            offset_cm=10,
            width_cm=1.5,
            start_cm=35,
            length_cm=20,
        ),
        edge_break=1,
        liner_start_cm=35,
        liner_length_cm=20,
    )
    turned = accept(
        _manufacturing_part(
            clipped,
            "edge_break",
            (0, 0),
            "1",
            offset_cm=10,
            width_cm=1.5,
            turns=1,
        ),
        edge_break=1,
        allow_rotation=1,
    )
    assert turned["rotated"] is True
    mirrored = accept(
        _manufacturing_part(
            clipped,
            "edge_break",
            (0, 0),
            "1",
            offset_cm=10,
            width_cm=1.5,
            mirrored=True,
        ),
        edge_break=1,
    )
    assert mirrored["rotated"] is False


def test_client_l_export_normalizes_and_reimports(tmp_path):
    client_path = tmp_path / "l-notch-client.dxf"
    env = os.environ.copy()
    env["L_NOTCH_DXF_OUT"] = str(client_path)
    subprocess.run(
        ["node", str(ROOT / "tests" / "js" / "secure_dxf_topology_export.test.js")],
        check=True,
        env=env,
    )
    raw = client_path.read_text(encoding="ascii").replace("\r\n", "\n")
    tokens = raw.split("\n")
    lengths = []
    for index, token in enumerate(tokens[:-12]):
        if token != "LINE" or tokens[index + 2] != "GEOMETRY":
            continue
        x1 = float(tokens[index + 4])
        y1 = float(tokens[index + 6])
        x2 = float(tokens[index + 10])
        y2 = float(tokens[index + 12])
        lengths.append(round(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, 3))
    assert 199 in lengths
    assert 99 in lengths
    assert 200 not in lengths
    assert 100 not in lengths
    normalized_path = tmp_path / "l-notch-normalized.dxf"
    normalized_path.write_bytes(rebuild_autocad_dxf(client_path.read_bytes()))
    order = _board(
        [
            _door(
                piece_instance_id="l-1",
                piece_type="L-Shaped Corner",
                width_cm=40,
                length_cm=40,
                cut_width_cm=40,
                cut_length_cm=40,
                clipped_corner_width_cm=20,
                clipped_corner_length_cm=30,
                edge_break=1,
                liner_reference_side="edge_break",
                liner_offset_cm=2,
                liner_width_cm=1.5,
            )
        ],
        default_edge_type="band-1",
    )
    piece = _import_banded(str(normalized_path), order, kerf_mm=3)["sheets"][0]["pieces"][0]
    assert piece["w"] == 40
    assert piece["h"] == 40
    assert float(piece["clipped_corner_width_cm"]) == 20
    assert piece["overlays"][0]["kind"] == "liner"


def test_system_corner_geometry_with_repeated_equal_envelopes_reimports():
    l_piece = LinerPiece(
        "L-Shaped Corner",
        20,
        30,
        clipped_corner_width_cm=5,
        clipped_corner_length_cm=6,
    )
    clipped_piece = LinerPiece(
        "Clipped Corner",
        20,
        30,
        clipped_corner_width_cm=5,
        clipped_corner_length_cm=6,
    )
    mixed = [clipped_piece, l_piece, l_piece, clipped_piece, l_piece, l_piece, l_piece]
    parts = []
    for index, piece in enumerate(mixed):
        column = index % 5
        row = index // 5
        origin = (column * 210.0, row * 310.0)
        outline = [
            _sheet_point(point, origin)
            for point in piece_polygon_mm(piece)
        ]
        parts.append({"outline": outline, "label": str(index + 1)})

    order = _board(
        [
            _door(
                piece_instance_id="corner-l",
                qty=5,
                extra_liner=0,
                piece_type="L-Shaped Corner",
                width_cm=20,
                length_cm=30,
                cut_width_cm=20,
                cut_length_cm=30,
                allow_rotation=1,
                clipped_corner_width_cm=5,
                clipped_corner_length_cm=6,
            ),
            _door(
                piece_instance_id="corner-clipped",
                qty=2,
                extra_liner=0,
                piece_type="Clipped Corner",
                width_cm=20,
                length_cm=30,
                cut_width_cm=20,
                cut_length_cm=30,
                allow_rotation=1,
                clipped_corner_width_cm=5,
                clipped_corner_length_cm=6,
                edge_break_only=1,
            ),
        ]
    )

    snapshot = _import_banded(
        _normalize(_write_geometry_sheet(parts)),
        order,
        kerf_mm=3,
    )

    pieces = snapshot["sheets"][0]["pieces"]
    assert len(pieces) == 7
    assert [piece["source_piece_no"] for piece in pieces] == [
        2,
        1,
        1,
        2,
        1,
        1,
        1,
    ]
    assert sorted(piece["piece_instance_id"] for piece in pieces) == [
        "corner-clipped:1",
        "corner-clipped:2",
        "corner-l:1",
        "corner-l:2",
        "corner-l:3",
        "corner-l:4",
        "corner-l:5",
    ]
