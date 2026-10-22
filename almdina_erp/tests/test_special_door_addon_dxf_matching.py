"""Special doors stay non-rectangular and match add-ons as a group."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

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


if __name__ == "__main__":
    unittest.main()
