"""Special doors stay non-rectangular and match add-ons as a group."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf
import pytest

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    ContourCandidate,
    ExpectedPieceEvidence,
    resolve_contour_ownership,
)
from almdina_erp.almdina_erp.domain.cutting.special_addon_match import (
    SpecialContourRecord,
    SpecialExpectedRecord,
    match_special_addon_group,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import (
    ExtraAddonPieceInput,
    ExtraAddonRates,
    calculate_extra_addon_pricing,
    normalize_extra_double_sides,
)
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import LinerPiece, liner_toolpath_mm
from almdina_erp.almdina_erp.domain.cutting.plan_settings import PlanSettings
from almdina_erp.almdina_erp.services import strict_dxf_import_service as strict

legacy = dxf_import_service

SHEET = dxf_import_service.SHEET_OUTLINE_LAYER
CUT = dxf_import_service.CUT_PATH_LAYER


def _present(error: DxfImportError) -> str:
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issue

    return "\n".join(present_issue(item).problem for item in error.issues)


def _write(doc) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    doc.saveas(handle.name)
    return handle.name


def _polygon(msp, points, *, layer: str) -> None:
    corners = tuple(points)
    for start, end in zip(corners, (*corners[1:], corners[0])):
        msp.add_line(start, end, dxfattribs={"layer": layer})


def _chamfer(x: float, y: float, width: float, height: float):
    return (
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x + 40, y + height),
        (x, y + height - 40),
    )


def _piece(**overrides):
    values = {
        "cut_width_cm": 60,
        "cut_length_cm": 80,
        "width_cm": 60,
        "length_cm": 80,
        "qty": 1,
        "piece_type": "Special",
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_full_door_double": 0,
        "extra_recessed_handle_cutout": 0,
        "extra_double": 0,
        "allow_rotation": 0,
        "liner_reference_side": "",
        "liner_offset_cm": 0,
        "liner_width_cm": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _order(pieces):
    return SimpleNamespace(
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=5,
        pieces=pieces,
    )


def _sheet(msp) -> None:
    _polygon(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer=SHEET)


class SpecialDoorAddonDxfMatchingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.paths: list[str] = []

    def tearDown(self) -> None:
        for path in self.paths:
            Path(path).unlink(missing_ok=True)

    def _parse(self, doc, order):
        path = _write(doc)
        self.paths.append(path)
        with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
            return dxf_import_service.parse_production_dxf("/private/files/special.dxf", order)

    def _doc(self):
        doc = ezdxf.new("R2010")
        _sheet(doc.modelspace())
        return doc, doc.modelspace()

    def test_rectangle_cannot_match_special_and_irregular_cannot_match_regular(self) -> None:
        from almdina_erp.almdina_erp.domain.cutting.dxf_topology import DxfTopologyError

        rectangle = ContourCandidate(1, ((0, 0), (600, 0), (600, 800), (0, 800)))
        irregular = ContourCandidate(2, _chamfer(0, 0, 600, 800))
        special = ExpectedPieceEvidence(600, 800, False, piece_type="Special")
        regular = ExpectedPieceEvidence(600, 800, False, piece_type="Regular")
        with self.assertRaises(DxfTopologyError) as special_error:
            resolve_contour_ownership((rectangle,), (special,), dimension_tolerance=2, geometry_tolerance=0.25)
        self.assertEqual(special_error.exception.code, "SPECIAL_OUTLINE_IS_RECTANGLE")
        with self.assertRaises(DxfTopologyError) as regular_error:
            resolve_contour_ownership((irregular,), (regular,), dimension_tolerance=2, geometry_tolerance=0.25)
        self.assertEqual(regular_error.exception.code, "REGULAR_OUTLINE_NOT_RECTANGLE")

    def test_omitted_piece_type_keeps_dimension_only_matching(self) -> None:
        rectangle = ContourCandidate(1, ((0, 0), (600, 0), (600, 800), (0, 800)))
        resolved = resolve_contour_ownership(
            (rectangle,),
            (ExpectedPieceEvidence(600, 800, False, arbitrary_outline=True),),
            dimension_tolerance=2,
            geometry_tolerance=0.25,
        )
        self.assertEqual(len(resolved.parts), 1)

    def test_glass_and_corners_are_not_reclassified_as_special(self) -> None:
        rectangle = ContourCandidate(1, ((0, 0), (400, 0), (400, 600), (0, 600)))
        notch = ContourCandidate(2, ((0, 0), (500, 0), (500, 200), (200, 200), (200, 500), (0, 500)))
        glass = resolve_contour_ownership(
            (rectangle,),
            (ExpectedPieceEvidence(400, 600, False, piece_type="Glass"),),
            dimension_tolerance=2,
            geometry_tolerance=0.25,
        )
        clipped = resolve_contour_ownership(
            (rectangle,),
            (ExpectedPieceEvidence(400, 600, False, piece_type="Clipped Corner"),),
            dimension_tolerance=2,
            geometry_tolerance=0.25,
        )
        shaped = resolve_contour_ownership(
            (notch,),
            (ExpectedPieceEvidence(500, 500, False, piece_type="L-Shaped Corner"),),
            dimension_tolerance=2,
            geometry_tolerance=0.25,
        )
        self.assertEqual(len(glass.parts), 1)
        self.assertEqual(len(clipped.parts), 1)
        self.assertEqual(len(shaped.parts), 1)

    def test_same_size_regular_and_special_keep_their_outlines(self) -> None:
        doc, msp = self._doc()
        _polygon(msp, ((0, 0), (600, 0), (600, 800), (0, 800)), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        snapshot = self._parse(doc, _order([
            _piece(piece_type="Regular"),
            _piece(piece_type="Special"),
        ]))
        pieces = snapshot["sheets"][0]["pieces"]
        by_type = {piece["piece_type"] for piece in pieces}
        self.assertEqual(by_type, {"Regular", "Special"})
        regular = next(piece for piece in pieces if piece["piece_type"] == "Regular")
        special = next(piece for piece in pieces if piece["piece_type"] == "Special")
        self.assertGreater(
            len(special["geometry"]["outer"]),
            len(regular["geometry"]["outer"]),
        )

    def test_same_size_specials_accept_liner_on_either_shape(self) -> None:
        for liner_on_second in (False, True):
            with self.subTest(liner_on_second=liner_on_second):
                doc, msp = self._doc()
                _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
                _polygon(msp, ((0, 900), (600, 900), (520, 1700), (0, 1700)), layer=CUT)
                if liner_on_second:
                    msp.add_line((80, 1020), (80, 1580), dxfattribs={"layer": "Liner"})
                else:
                    msp.add_line((80, 120), (80, 680), dxfattribs={"layer": "Liner"})
                snapshot = self._parse(doc, _order([
                    _piece(extra_liner=1),
                    _piece(),
                ]))
                pieces = snapshot["sheets"][0]["pieces"]
                self.assertEqual(len(pieces), 2)
                owners = [piece for piece in pieces if piece.get("overlays")]
                self.assertEqual(len(owners), 1)
                self.assertEqual(owners[0]["piece_type"], "Special")
                self.assertEqual(owners[0]["overlays"][0]["kind"], "liner")

    def test_missing_extra_and_regular_liner_are_group_failures(self) -> None:
        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        with self.assertRaises(DxfImportError) as missing:
            self._parse(doc, _order([_piece(extra_liner=1), _piece()]))
        self.assertEqual(missing.exception.codes, ["SPECIAL_ADDON_GROUP_MISSING"])
        self.assertIsNone(missing.exception.issues[0].target.source_piece_no)
        self.assertIn("60", _present(missing.exception))

        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        msp.add_line((80, 120), (80, 680), dxfattribs={"layer": "Liner"})
        msp.add_line((80, 1020), (80, 1580), dxfattribs={"layer": "Liner"})
        with self.assertRaises(DxfImportError) as extra:
            self._parse(doc, _order([_piece(extra_liner=1), _piece()]))
        self.assertEqual(extra.exception.codes, ["SPECIAL_ADDON_GROUP_EXTRA"])

        doc, msp = self._doc()
        _polygon(msp, ((0, 0), (600, 0), (600, 800), (0, 800)), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        msp.add_line((80, 120), (80, 680), dxfattribs={"layer": "Liner"})
        with self.assertRaises(DxfImportError) as borrowed:
            self._parse(doc, _order([
                _piece(piece_type="Regular"),
                _piece(piece_type="Special", extra_liner=1),
            ]))
        self.assertEqual(borrowed.exception.codes, ["SPECIAL_ADDON_GROUP_MISSING"])
        self.assertEqual(borrowed.exception.issues[0].params.get("found_on_piece_type"), "Regular")

    def test_shared_addons_must_stay_on_one_special_door(self) -> None:
        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        msp.add_line((80, 120), (80, 680), dxfattribs={"layer": "Liner"})
        msp.add_line((500, 120), (500, 680), dxfattribs={"layer": "Rear Groove"})
        _polygon(msp, ((120, 300), (260, 300), (260, 460), (120, 460)), layer="Handle Recess")
        snapshot = self._parse(doc, _order([
            _piece(extra_liner=1, extra_back_groove=1, extra_recessed_handle_cutout=1),
            _piece(),
        ]))
        owners = [piece for piece in snapshot["sheets"][0]["pieces"] if piece.get("overlays")]
        self.assertEqual(len(owners), 1)
        self.assertEqual(
            {item["kind"] for item in owners[0]["overlays"]},
            {"liner", "back_groove", "recessed_handle_cutout"},
        )

        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        msp.add_line((80, 120), (80, 680), dxfattribs={"layer": "Liner"})
        _polygon(msp, ((120, 1100), (260, 1100), (260, 1260), (120, 1260)), layer="Handle Recess")
        with self.assertRaises(DxfImportError) as split:
            self._parse(doc, _order([
                _piece(extra_liner=1, extra_recessed_handle_cutout=1),
                _piece(),
            ]))
        self.assertEqual(split.exception.codes, ["SPECIAL_ADDON_GROUP_SPLIT"])
        self.assertIsNone(split.exception.issues[0].target.source_piece_no)

    def test_back_groove_presence_and_distinct_groups(self) -> None:
        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        msp.add_line((500, 100), (500, 700), dxfattribs={"layer": "Rear Groove"})
        snapshot = self._parse(doc, _order([_piece(extra_back_groove=1)]))
        self.assertEqual(snapshot["sheets"][0]["pieces"][0]["overlays"][0]["kind"], "back_groove")

        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        with self.assertRaises(DxfImportError) as missing:
            self._parse(doc, _order([_piece(extra_back_groove=1)]))
        self.assertEqual(missing.exception.codes, ["SPECIAL_ADDON_GROUP_MISSING"])
        self.assertEqual(missing.exception.issues[0].params["overlay_kind"], "back_groove")

        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        _polygon(msp, _chamfer(0, 1000, 500, 700), layer=CUT)
        msp.add_line((80, 1100), (80, 1600), dxfattribs={"layer": "Liner"})
        with self.assertRaises(DxfImportError) as crossed:
            self._parse(doc, _order([
                _piece(extra_liner=1),
                _piece(cut_width_cm=50, cut_length_cm=70, width_cm=50, length_cm=70),
            ]))
        self.assertIn(crossed.exception.codes[0], {"SPECIAL_ADDON_GROUP_MISSING", "SPECIAL_ADDON_GROUP_EXTRA"})

    def test_copies_rotation_circle_and_ambiguous_binding(self) -> None:
        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        msp.add_line((80, 120), (80, 680), dxfattribs={"layer": "Liner"})
        msp.add_line((80, 1020), (80, 1580), dxfattribs={"layer": "Liner"})
        snapshot = self._parse(doc, _order([_piece(qty=2, extra_liner=1)]))
        self.assertEqual(len(snapshot["sheets"][0]["pieces"]), 2)
        self.assertTrue(all(piece.get("overlays") for piece in snapshot["sheets"][0]["pieces"]))

        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 800, 600), layer=CUT)
        snapshot = self._parse(doc, _order([_piece(allow_rotation=1)]))
        self.assertTrue(snapshot["sheets"][0]["pieces"][0]["rotated"])

        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 800, 600), layer=CUT)
        with self.assertRaises(DxfImportError) as forbidden:
            self._parse(doc, _order([_piece(allow_rotation=0)]))
        self.assertEqual(forbidden.exception.codes, ["FORBIDDEN_ROTATION"])

        doc, msp = self._doc()
        msp.add_circle((200, 200), 200, dxfattribs={"layer": CUT})
        snapshot = self._parse(doc, _order([
            _piece(cut_width_cm=40, cut_length_cm=40, width_cm=40, length_cm=40),
        ]))
        piece = snapshot["sheets"][0]["pieces"][0]
        self.assertEqual(piece["piece_type"], "Special")
        self.assertGreater(len(piece["geometry"]["outer"]), 4)

        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        _polygon(msp, _chamfer(0, 900, 600, 800), layer=CUT)
        msp.add_line((100, 200), (100, 1400), dxfattribs={"layer": "Liner"})
        with self.assertRaises(DxfImportError) as ambiguous:
            self._parse(doc, _order([_piece(extra_liner=1), _piece()]))
        self.assertEqual(ambiguous.exception.codes, ["SPECIAL_OVERLAY_AMBIGUOUS"])

    def test_old_special_row_without_addon_fields_still_imports(self) -> None:
        doc, msp = self._doc()
        _polygon(msp, _chamfer(0, 0, 600, 800), layer=CUT)
        legacy = SimpleNamespace(
            cut_width_cm=60,
            cut_length_cm=80,
            width_cm=60,
            length_cm=80,
            qty=1,
            piece_type="Special",
            allow_rotation=0,
        )
        snapshot = self._parse(doc, _order([legacy]))
        self.assertEqual(snapshot["sheets"][0]["pieces"][0]["piece_type"], "Special")
        self.assertNotIn("overlays", snapshot["sheets"][0]["pieces"][0])

    def test_group_matcher_is_deterministic_and_rotation_aware(self) -> None:
        contours = (
            SpecialContourRecord(1, 60, 80, frozenset({"liner"}), 0),
            SpecialContourRecord(2, 60, 80, frozenset(), 1),
        )
        expected = (
            SpecialExpectedRecord(0, 60, 80, True, frozenset()),
            SpecialExpectedRecord(1, 60, 80, True, frozenset({"liner"})),
        )
        first = match_special_addon_group(contours, expected, tolerance_cm=0.2)
        second = match_special_addon_group(contours, expected, tolerance_cm=0.2)
        self.assertTrue(first.ok)
        self.assertEqual(first.mapping, second.mapping)
        self.assertEqual(first.mapping[1], 1)
        blocked = match_special_addon_group(
            (SpecialContourRecord(1, 80, 60, frozenset({"liner"}), None),),
            (SpecialExpectedRecord(0, 60, 80, False, frozenset({"liner"}), source_piece_no=3, copy_no=1),),
            tolerance_cm=0.2,
        )
        self.assertEqual(blocked.code, "FORBIDDEN_ROTATION")
        self.assertEqual(blocked.params["source_piece_no"], 3)

    def test_special_addons_use_the_same_rates_and_no_fake_sides(self) -> None:
        rates = ExtraAddonRates(
            double_usd=4,
            full_door_double_usd=6,
            liner_usd=2.5,
            back_groove_usd=3,
            recessed_handle_cutout_usd=1.25,
        )
        special = calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(
                piece_type="Special",
                qty=2,
                double=True,
                liner=True,
                back_groove=True,
                recessed_handle_cutout=True,
            )],
            rates=rates,
        )
        regular = calculate_extra_addon_pricing(
            [ExtraAddonPieceInput(
                piece_type="Regular",
                qty=2,
                double=True,
                liner=True,
                back_groove=True,
                recessed_handle_cutout=True,
            )],
            rates=rates,
        )
        self.assertEqual(special.total_usd, regular.total_usd)
        self.assertEqual(normalize_extra_double_sides(["edge_long_right"], piece_type="Special", enabled=True), ())
        self.assertEqual(normalize_extra_double_sides([], piece_type="Special", enabled=True), ())


def _row(number, **values):
    data = dict(
        name=f"row-{number}", piece_instance_id=f"piece:{number}",
        width_cm=51.9, length_cm=196.4, cut_width_cm=51.9, cut_length_cm=196.4,
        qty=1, piece_type="Regular", allow_rotation=0,
        extra_liner=0, extra_back_groove=1, extra_recessed_handle_cutout=0,
        recessed_handle_reference_side="edge_width_bottom", recessed_handle_offset_cm=20,
        recessed_handle_width_cm=2, recessed_handle_start_cm=10, recessed_handle_length_cm=20,
        liner_reference_side="edge_long_left", liner_offset_cm=5, liner_width_cm=1.8,
        liner_start_cm=10, liner_length_cm=170,
        back_groove_reference_side="edge_long_right", back_groove_offset_cm=1,
        back_groove_width_cm=0.7, back_groove_start_cm=10, back_groove_length_cm=170,
    )
    data.update(values)
    return SimpleNamespace(**data)


def _fixture(*, reverse=False, text=False, liners=(True, False), same_signature=False, equivalent=False, handle=False):
    rows = [_row(i, width_cm=8, length_cm=10, cut_width_cm=8, cut_length_cm=10,
                 extra_back_groove=0) for i in range(1, 11)]
    rows += [_row(11, extra_liner=1), _row(12, extra_liner=int(same_signature), liner_offset_cm=5 if equivalent else 15,
                                  extra_recessed_handle_cutout=int(handle))]
    order = SimpleNamespace(pieces=rows, trim_margin_mm=0, board_width_cm=122,
                            board_length_cm=244, full_board_width_mm=1220,
                            full_board_length_mm=2440, kerf_mm=5)
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    def rectangle(x, y, w, h, layer):
        msp.add_lwpolyline([(x,y), (x+w,y), (x+w,y+h), (x,y+h)], close=True,
                          dxfattribs={"layer": layer})
    rectangle(0, 0, 1220, 2440, "SHEET_OUTLINE")
    for i in range(10):
        rectangle(10 + i*100, 2200, 80, 100, "CUT_PATH")
    for slot in ((1, 0) if reverse else (0, 1)):
        x = 10 + slot*600
        rectangle(x, 100, 519, 1964, "CUT_PATH")
        # Put row 11 on the contour that size-first binding assigns to row 12.
        owner = rows[11] if slot else rows[10]
        for kind, prefix, layer in (("back_groove", "back_groove", "Rear Groove"),
                                    ("liner", "liner", "Liner"),
                                    ("recessed_handle_cutout", "recessed_handle", "Handle Recess")):
            if kind == "liner" and not (liners[slot] or same_signature):
                continue
            if kind == "recessed_handle_cutout" and not owner.extra_recessed_handle_cutout:
                continue
            path = liner_toolpath_mm(
                LinerPiece("Regular", 51.9, 196.4),
                getattr(owner, prefix+"_reference_side"), getattr(owner, prefix+"_offset_cm"),
                getattr(owner, prefix+"_width_cm"), 5,
                getattr(owner, prefix+"_start_cm"), getattr(owner, prefix+"_length_cm"),
            )
            msp.add_lwpolyline([(x+px, 2064-py) for px,py in path],
                              dxfattribs={"layer": layer})
        if text:
            # Misleading TEXT must not override manufacturing evidence.
            msp.add_text("12.1" if slot == 0 else "11.1", dxfattribs={
                "layer": "TEXT", "insert": (x+200, 1000), "height": 20})
    return doc, order


def _parse(tmp_path, doc, order, parser):
    path = tmp_path / "identity.dxf"
    doc.saveas(path)
    with patch.object(legacy.frappe, "get_site_path", return_value=str(path)):
        if parser == "strict":
            return strict.parse_production_dxf("/private/files/identity.dxf", order,
                settings=PlanSettings(optimization_mode="Auto", machine_type="CNC",
                    optimization_time_limit_sec=5, kerf_mm=5, preferred_trim_mm=0))
        return legacy.parse_production_dxf("/private/files/identity.dxf", order)


@pytest.mark.parametrize("parser", ["legacy", "strict"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("text", [False, True])
def test_reference_11_12_identity_survives_both_import_stages(tmp_path, parser, reverse, text):
    doc, order = _fixture(reverse=reverse, text=text)
    snapshot = _parse(tmp_path, doc, order, parser)
    pieces = {p["source_piece_no"]: p for s in snapshot["sheets"] for p in s["pieces"]}
    assert {o["kind"] for o in pieces[11]["overlays"]} == {"liner", "back_groove"}
    assert {o["kind"] for o in pieces[12]["overlays"]} == {"back_groove"}
    assert pieces[11]["x"] < pieces[12]["x"]
    if parser == "strict":
        assert pieces[11]["piece_instance_id"] == "piece:11:1"
        assert pieces[12]["piece_instance_id"] == "piece:12:1"


@pytest.mark.parametrize("parser", ["legacy", "strict"])
@pytest.mark.parametrize("liners", [(False, False), (True, True)])
def test_real_missing_or_extra_liner_is_rejected(tmp_path, parser, liners):
    doc, order = _fixture(liners=liners)
    with pytest.raises(legacy.DxfImportError) as error:
        _parse(tmp_path, doc, order, parser)
    assert error.value.codes == (["PIECE_IDENTITY_MISSING", "PERSISTED_CUT_SPECS"]
                                 if parser == "strict" else ["PIECE_IDENTITY_MISSING"])
    assert error.value.issues[0].params["identity_unproven"] is True
    assert error.value.issues[0].target.source_piece_no is None


@pytest.mark.parametrize("parser", ["legacy", "strict"])
def test_equal_signatures_use_actual_machining_parameters(tmp_path, parser):
    doc, order = _fixture(same_signature=True)
    snapshot = _parse(tmp_path, doc, order, parser)
    pieces = {p["source_piece_no"]: p for s in snapshot["sheets"] for p in s["pieces"]}
    assert pieces[11]["x"] < pieces[12]["x"]


@pytest.mark.parametrize("parser", ["legacy", "strict"])
def test_handle_recess_also_distinguishes_same_size_doors(tmp_path, parser):
    doc, order = _fixture(handle=True)
    snapshot = _parse(tmp_path, doc, order, parser)
    pieces = {p["source_piece_no"]: p for sheet in snapshot["sheets"] for p in sheet["pieces"]}
    assert {o["kind"] for o in pieces[11]["overlays"]} == {"liner", "back_groove"}
    assert {o["kind"] for o in pieces[12]["overlays"]} == {"back_groove", "recessed_handle_cutout"}
    assert pieces[11]["x"] < pieces[12]["x"]


def test_existing_group_matcher_backtracks_instead_of_greedy_assignment():
    # First contour can take either orientation; second can only take row 1.
    contours = (SpecialContourRecord(1, 60, 80, frozenset()),
                SpecialContourRecord(2, 80, 60, frozenset()))
    expected = (SpecialExpectedRecord(0, 60, 80, True, frozenset()),
                SpecialExpectedRecord(1, 60, 80, False, frozenset()))
    result = match_special_addon_group(contours, expected, tolerance_cm=0.2)
    assert result.ok
    assert result.mapping == {1: 1, 2: 0}


@pytest.mark.parametrize("parser", ["legacy", "strict"])
def test_manufacturing_equivalent_copies_keep_stable_identity(tmp_path, parser):
    mappings = []
    for reverse in (False, True):
        doc, order = _fixture(reverse=reverse, same_signature=True, equivalent=True)
        snapshot = _parse(tmp_path, doc, order, parser)
        mappings.append({p["source_piece_no"]: p["x"]
                         for sheet in snapshot["sheets"] for p in sheet["pieces"]})
    assert mappings[0] == mappings[1]
    assert mappings[0][11] < mappings[0][12]


def test_group_matching_rejects_hall_deficit_without_factorial_search():
    # Every contour has a candidate, but 32 liners cannot consume 31 liner copies.
    contours = tuple(SpecialContourRecord(i, 60, 80, frozenset({"liner"})) for i in range(32))
    expected = tuple(SpecialExpectedRecord(i, 60, 80, False,
                     frozenset({"liner"}) if i < 31 else frozenset()) for i in range(32))
    result = match_special_addon_group(contours, expected, tolerance_cm=0.2)
    assert not result.ok
    assert result.code == "SPECIAL_ADDON_GROUP_EXTRA"


if __name__ == "__main__":
    unittest.main()
