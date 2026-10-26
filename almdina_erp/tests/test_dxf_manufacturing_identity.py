"""Exact manufacturing identity must not inherit Topology's discovery tolerance."""

from collections import Counter
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf
import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    dimensions_match_exact,
)
from almdina_erp.almdina_erp.services import dxf_import_service as legacy
from almdina_erp.almdina_erp.services import strict_dxf_import_service as strict


def order_for(sizes):
    return SimpleNamespace(
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=5,
        pieces=[
            SimpleNamespace(
                name=f"row-{i}",
                piece_instance_id=f"fixture:{i}",
                piece_type="Regular",
                width_cm=w,
                length_cm=h,
                cut_width_cm=w,
                cut_length_cm=h,
                qty=qty,
                allow_rotation=1,
            )
            for i, (w, h, qty) in enumerate(sizes, 1)
        ],
    )


def write_plan(path, sizes, *, reverse=False, text=False, layer="GEOMETRY"):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (1220, 0), (1220, 2440), (0, 2440)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    instances = [(w, h) for w, h, qty in sizes for _ in range(qty)]
    contours = []
    for slot, (w, h) in enumerate(instances):
        x, y = 10 + (slot % 2) * 605, 10 + (slot // 2) * 330
        contours.append(
            [(x, y), (x + w * 10, y), (x + w * 10, y + h * 10), (x, y + h * 10)]
        )
    for points in reversed(contours) if reverse else contours:
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
    if text:
        msp.add_text("999.999", dxfattribs={"layer": "TEXT", "insert": (200, 200)})
    doc.saveas(path)


def parse(path, order, parser="strict"):
    with patch.object(legacy.frappe, "get_site_path", return_value=str(path)):
        if parser == "legacy":
            return legacy.parse_production_dxf("/private/files/identity.dxf", order)
        return strict.parse_production_dxf(
            "/private/files/identity.dxf",
            order,
            settings=PlanSettings("Auto", "CNC", 5, 5, 0),
        )


@pytest.mark.parametrize(
    "sizes",
    [
        [(59.8, 31, 2), (59.8, 30.8, 1)],
        [(59.8, 29.9, 2), (60, 29.9, 2), (60, 29.9, 2)],
        [(59.8, 31, 2), (59.8, 30.9, 1)],
    ],
)
@pytest.mark.parametrize("parser", ["legacy", "strict"])
@pytest.mark.parametrize("reverse,text", [(False, False), (True, False), (True, True)])
def test_near_sizes_do_not_inherit_approximate_topology_identity(
    tmp_path, sizes, parser, reverse, text
):
    path = tmp_path / "identity.dxf"
    write_plan(path, sizes, reverse=reverse, text=text)
    order = order_for(sizes)
    snapshot = parse(path, order, parser)
    pieces = [p for s in snapshot["sheets"] for p in s["pieces"]]
    for p in pieces:
        row = order.pieces[p["source_piece_no"] - 1]
        assert dimensions_match_exact(
            p["w"], p["h"], row.cut_width_cm, row.cut_length_cm
        )
    assert Counter(p["source_piece_no"] for p in pieces) == Counter(
        {i: r.qty for i, r in enumerate(order.pieces, 1)}
    )


@pytest.mark.parametrize("layer", ["GEOMETRY", "CUT_PATH"])
def test_real_size_mismatch_reports_residuals_without_inventing_a_door(tmp_path, layer):
    path = tmp_path / "wrong-size.dxf"
    write_plan(path, [(59.8, 31, 2), (59.8, 30.7, 1)], layer=layer)
    with pytest.raises(legacy.DxfImportError) as error:
        parse(path, order_for([(59.8, 31, 2), (59.8, 30.8, 1)]))
    item = error.value.issues[0]
    assert item.code == "EXPECTED_PIECE_MISMATCH"
    assert item.target.source_piece_no is None
    assert item.params["missing_count"] == item.params["extra_count"] == 1
    assert item.params["missing_sizes"] == ["59.8 × 30.8 سم"]
    assert item.params["extra_sizes"] == ["59.8 × 30.7 سم"]


def test_exact_parity_does_not_treat_a_near_square_as_unrotated():
    order = order_for([(60, 59.8, 1)])
    pieces = [dict(id=1, w=59.8, h=60, piece_type="Regular", _expected_piece_index=0)]
    matched = legacy._match_pieces_to_order(pieces, order)
    assert matched[0]["rotated"] is True


def test_strict_does_not_guess_again_when_a_proven_copy_is_duplicated():
    from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
        build_order_piece_cut_specs,
    )

    order = order_for([(59.8, 31, 2)])
    specs = strict._bind_persisted_cut_dimensions(
        order, build_order_piece_cut_specs(order)
    )
    pieces = [
        dict(
            id=i,
            label="1.1",
            source_piece_no=1,
            copy_no=1,
            piece_type="Regular",
            w=59.8,
            h=31,
        )
        for i in (1, 2)
    ]
    errors = strict._apply_strict_dimension_contract(
        {"sheets": [{"pieces": pieces}]}, specs, order=order
    )
    assert [e.code for e in errors] == ["PIECE_IDENTITY_MISSING", "PIECE_MISSING"]
    assert pieces[1]["copy_no"] == 1


@pytest.mark.parametrize(
    "piece_type", ["Regular", "Glass", "L-Shaped Corner", "Clipped Corner"]
)
def test_group_eligibility_uses_exact_dimensions_for_every_non_special_type(piece_type):
    from almdina_erp.almdina_erp.domain.cutting.special_addon_match import (
        SpecialContourRecord,
        SpecialExpectedRecord,
        match_special_addon_group,
    )

    result = match_special_addon_group(
        [SpecialContourRecord(1, 59.8, 31, frozenset(), 0)],
        [SpecialExpectedRecord(0, 60, 31, True, frozenset(), piece_type=piece_type)],
        tolerance_cm=0.2,
    )
    assert not result.ok
    assert not result.mapping


@pytest.mark.parametrize(
    "width,accepted", [(59.8, True), (60, True), (60.001, False), (59.799, False)]
)
def test_special_group_keeps_the_one_sided_two_mm_contract(width, accepted):
    from almdina_erp.almdina_erp.domain.cutting.special_addon_match import (
        SpecialContourRecord,
        SpecialExpectedRecord,
        match_special_addon_group,
    )

    result = match_special_addon_group(
        [SpecialContourRecord(1, width, 31, frozenset(), 0)],
        [SpecialExpectedRecord(0, 60, 31, False, frozenset())],
        tolerance_cm=0.2,
    )
    assert result.ok is accepted


def test_full_assignment_repairs_a_greedy_special_envelope_conflict():
    order = order_for([(60, 31, 1), (60.2, 31, 1)])
    for row in order.pieces:
        row.piece_type = "Special"
    pieces = [
        dict(id=i + 1, w=w, h=31, piece_type="Special", _expected_piece_index=i)
        for i, w in enumerate((60, 59.8))
    ]
    matched = legacy._match_pieces_to_order(pieces, order)
    assert [p["source_piece_no"] for p in matched] == [2, 1]


@pytest.mark.parametrize("n", [100, 500])
@pytest.mark.parametrize("repeated", [False, True])
def test_large_identity_groups_remain_bounded(n, repeated):
    sizes = [(20 if repeated else 20 + i / 10, 80, 1) for i in range(n)]
    order = order_for(sizes)
    # Wrong discovery indexes force global repair for distinct sizes.
    pieces = [
        dict(id=i + 1, w=w, h=h, piece_type="Regular", _expected_piece_index=n - i - 1)
        for i, (w, h, _) in enumerate(sizes)
    ]
    started = perf_counter()
    matched = legacy._match_pieces_to_order(pieces, order)
    elapsed = perf_counter() - started
    assert len({(p["source_piece_no"], p["copy_no"]) for p in matched}) == n
    assert all(
        dimensions_match_exact(
            p["w"], p["h"], order.pieces[p["source_piece_no"] - 1].cut_width_cm, 80
        )
        for p in matched
    )
    assert elapsed < 2.0, f"{n} pieces took {elapsed:.3f}s"


@pytest.mark.parametrize(
    "status,layer",
    [("Absent", "GEOMETRY"), ("Present", "GEOMETRY"), ("Legacy", "CUT_PATH")],
)
@pytest.mark.parametrize("language", ["ar", "en"])
def test_size_error_guidance_uses_the_actual_outline_layer(
    status, layer, language, monkeypatch
):
    import csv
    from pathlib import Path
    from almdina_erp.almdina_erp.presentation.cutting import (
        dxf_error_presenter as presenter,
    )

    order = order_for([(60, 31, 1)])
    snapshot = {
        "saw_center_status": status,
        "sheets": [
            {
                "pieces": [
                    dict(
                        id=1,
                        label="1.1",
                        source_piece_no=1,
                        copy_no=1,
                        piece_type="Regular",
                        w=60.1,
                        h=31,
                    ),
                ]
            }
        ],
    }
    monkeypatch.setattr(
        strict, "_legacy_parse_production_dxf", lambda *a, **kw: snapshot
    )
    monkeypatch.setattr(
        strict, "apply_adaptive_trim_to_fixed_dxf_layout", lambda snap, **kw: snap
    )
    with pytest.raises(legacy.DxfImportError) as error:
        strict.parse_production_dxf(
            "/private/files/proven.dxf",
            order,
            settings=PlanSettings("Auto", "CNC", 5, 5, 0),
        )
    item = error.value.issues[0]
    assert item.code == "CUT_SIZE_MISMATCH"
    assert item.params["outline_layer"] == layer
    if language == "ar":
        catalog = Path(__file__).resolve().parents[1] / "translations" / "ar.csv"
        with catalog.open() as handle:
            translations = {
                row[0]: row[1] for row in csv.reader(handle) if len(row) >= 2
            }
        monkeypatch.setattr(
            presenter, "_", lambda source: translations.get(source, source)
        )
    else:
        monkeypatch.setattr(presenter, "_", lambda source: source)
    presented = presenter.present_issue(item)
    assert layer in presented.action
    assert ("CUT_PATH" if layer == "GEOMETRY" else "GEOMETRY") not in presented.action
    assert presented.problem and presented.target and presented.action


@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_near_size_identity_and_liner_share_the_same_physical_rotation(tmp_path, turns):
    from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
        LinerPiece,
        liner_toolpath_mm,
        transform_point,
    )

    order = order_for([(59.8, 31, 1), (60, 31, 1)])
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (1220, 0), (1220, 2440), (0, 2440)],
        close=True,
        dxfattribs={"layer": "SHEET_OUTLINE"},
    )
    for slot, row in enumerate(order.pieces):
        row.extra_liner = 1
        row.liner_reference_side = "edge_long_left"
        row.liner_offset_cm = 5
        row.liner_width_cm = 1.8
        row.liner_start_cm = 3
        row.liner_length_cm = 20
        width, height = row.cut_width_cm * 10, row.cut_length_cm * 10

        def placed(point):
            x, y = transform_point(
                point, mirrored=False, quarter_turns=turns, width=width, height=height
            )
            return 10 + slot * 610 + x, 2000 - y

        msp.add_lwpolyline(
            [placed(p) for p in [(0, 0), (width, 0), (width, height), (0, height)]],
            close=True,
            dxfattribs={"layer": "GEOMETRY"},
        )
        path = liner_toolpath_mm(
            LinerPiece("Regular", row.cut_width_cm, row.cut_length_cm),
            "edge_long_left",
            5,
            1.8,
            5,
            3,
            20,
        )
        msp.add_lwpolyline([placed(p) for p in path], dxfattribs={"layer": "Liner"})
    path = tmp_path / "rotated.dxf"
    doc.saveas(path)
    snapshot = parse(path, order)
    pieces = [p for sheet in snapshot["sheets"] for p in sheet["pieces"]]
    assert {p["source_piece_no"] for p in pieces} == {1, 2}
    for p in pieces:
        row = order.pieces[p["source_piece_no"] - 1]
        assert p["cut_width_cm"] == row.cut_width_cm
        assert p["rotation_quarter_turns"] == turns
        assert len(p["overlays"]) == 1


def test_near_square_with_forbidden_exact_rotation_is_not_a_size_error():
    order = order_for([(60, 59.8, 1)])
    order.pieces[0].allow_rotation = 0
    pieces = [dict(id=1, w=59.8, h=60, piece_type="Regular", _expected_piece_index=0)]
    with pytest.raises(legacy.DxfImportError) as error:
        legacy._match_pieces_to_order(pieces, order)
    assert error.value.codes == ["FORBIDDEN_ROTATION"]
    assert error.value.issues[0].target.source_piece_no == 1
