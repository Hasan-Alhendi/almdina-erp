"""End-to-end strict snapshot ownership: 0/90/180/270 from one machining transform."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    liner_strip_polygon_mm,
    transform_point,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import OrderPieceCutSpec
from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
    _apply_strict_dimension_contract,
    _proxy_order,
)
from almdina_erp.almdina_erp.application.cutting.plan_revisions import PlanSettings


CUT_W, CUT_H = 54.9, 100.0
ADDONS = (
    ("liner", "liner", "edge_long_right", 10.0, 1.8),
    ("back_groove", "back_groove", "edge_long_left", 0.5, 0.7),
    ("recessed_handle_cutout", "recessed_handle", "edge_width_bottom", 13.0, 2.0),
)


def _row():
    data = dict(
        piece_instance_id="piece:26-00081-1",
        qty=1,
        extra_full_door_double=0,
        cut_width_cm=CUT_W,
        cut_length_cm=CUT_H,
    )
    for _kind, prefix, side, offset, width in ADDONS:
        data["extra_" + ("recessed_handle_cutout" if prefix == "recessed_handle" else prefix)] = 1
        data[prefix + "_reference_side" if prefix != "liner" else "liner_reference_side"] = side
        data[prefix + "_offset_cm"] = offset
        data[prefix + "_width_cm"] = width
        data[prefix + "_start_cm"] = 0
        data[prefix + "_length_cm"] = 0
    return SimpleNamespace(**data)


def _spec(*, allow_rotation=1):
    return OrderPieceCutSpec(
        row_index=1,
        finished_width_cm=Decimal("55.000"),
        finished_length_cm=Decimal("100.000"),
        cut_width_cm=Decimal("54.900"),
        cut_length_cm=Decimal("100.000"),
        width_deduction_mm=Decimal("1"),
        length_deduction_mm=Decimal("0"),
        allow_rotation=allow_rotation,
        piece_type="Regular",
        qty=1,
        side_profiles=(
            {"side": "long_right", "edge_type": "PVC", "thickness_mm": Decimal("1")},
        ),
    )


def _snapshot(turns, *, moved_kind=None):
    width, height = CUT_W * 10, CUT_H * 10
    next_width, next_height = (width, height) if turns % 2 == 0 else (height, width)
    def rotated_point(point, angle=turns):
        return list(transform_point(
            point, mirrored=False, quarter_turns=angle,
            width=width, height=height,
        ))
    source = LinerPiece("Regular", CUT_W, CUT_H)
    paths = []
    for kind, _prefix, side, offset, strip_width in ADDONS:
        original = liner_strip_polygon_mm(source, side, offset, strip_width)
        angle = (turns + 2) % 4 if moved_kind == kind else turns
        paths.append({
            "kind": kind,
            "geometry": {"path": [rotated_point(point, angle) for point in original], "closed": True},
        })
    return {
        "sheets": [{
            "pieces": [{
                "id": 1, "label": "1.1", "w": next_width / 10, "h": next_height / 10,
                "x": 0, "y": 0, "piece_type": "Regular",
                "geometry": {
                    "outer": [[0, 0], [next_width, 0], [next_width, next_height], [0, next_height]],
                },
                "overlays": paths,
            }],
        }],
    }


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_strict_snapshot_preserves_original_edge_and_three_machining_paths(turns):
    order = SimpleNamespace(pieces=[_row()])
    snapshot = _snapshot(turns)
    errors = _apply_strict_dimension_contract(snapshot, [_spec()], order=order)
    assert errors == []
    actual = snapshot["sheets"][0]["pieces"][0]
    assert actual["rotation_quarter_turns"] == turns
    assert actual["rotated"] == bool(turns % 2)
    assert actual["edge_long_right"] == 1
    assert actual["edge_width_top"] == 0
    assert actual["geometry"]["outer"] == _snapshot(turns)["sheets"][0]["pieces"][0]["geometry"]["outer"]
    assert len(actual["overlays"]) == 3


def test_strict_rejects_half_turn_when_allow_rotation_off():
    snapshot = _snapshot(2)
    errors = _apply_strict_dimension_contract(snapshot, [_spec(allow_rotation=0)], order=SimpleNamespace(pieces=[_row()]))
    assert any(error.code == "FORBIDDEN_ROTATION" for error in errors)
    assert "rotation_quarter_turns" not in snapshot["sheets"][0]["pieces"][0]


def test_strict_rejects_one_wrongly_rotated_extra():
    snapshot = _snapshot(1, moved_kind="liner")
    errors = _apply_strict_dimension_contract(snapshot, [_spec()], order=SimpleNamespace(pieces=[_row()]))
    assert errors
    assert "rotation_quarter_turns" not in snapshot["sheets"][0]["pieces"][0]
