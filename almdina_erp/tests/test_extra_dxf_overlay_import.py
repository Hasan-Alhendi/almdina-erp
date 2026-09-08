from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.almdina_erp.domain.orders.extra_addons import EXTRA_OVERLAY_LAYER_NAMES
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError


SHEET = dxf_import_service.SHEET_OUTLINE_LAYER
CUT = dxf_import_service.CUT_PATH_LAYER
LINER = "Liner"


def _write_dxf(doc) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    doc.saveas(handle.name)
    return handle.name


def _add_rectangle(msp, points, *, layer: str) -> None:
    corners = tuple(points)
    for start, end in zip(corners, (*corners[1:], corners[0])):
        msp.add_line(start, end, dxfattribs={"layer": layer})


def _order(
    *,
    piece_type: str,
    extra_liner: int = 0,
    extra_back_groove: int = 0,
    extra_recessed_handle_cutout: int = 0,
    cut_width_cm: float = 40,
    cut_length_cm: float = 60,
):
    return SimpleNamespace(
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=5,
        pieces=[
            SimpleNamespace(
                cut_width_cm=cut_width_cm,
                cut_length_cm=cut_length_cm,
                width_cm=cut_width_cm,
                length_cm=cut_length_cm,
                qty=1,
                allow_rotation=0,
                piece_type=piece_type,
                extra_liner=extra_liner,
                extra_back_groove=extra_back_groove,
                extra_full_door_double=0,
                extra_recessed_handle_cutout=extra_recessed_handle_cutout,
                extra_double=0,
            )
        ],
    )


def _extra_plan_doc(
    *,
    overlay_layer: str | None = LINER,
    overlay_on_cut_path: bool = False,
    overlay_points=None,
):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _add_rectangle(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer=SHEET)
    _add_rectangle(msp, ((0, 0), (400, 0), (400, 600), (0, 600)), layer=CUT)
    overlay = overlay_points or ((40, 40), (180, 40), (180, 160), (40, 160))
    if overlay_on_cut_path:
        _add_rectangle(msp, overlay, layer=CUT)
    elif overlay_layer:
        _add_rectangle(msp, overlay, layer=overlay_layer)
    return doc


def _reference_style_extra_plan_doc():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _add_rectangle(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer=SHEET)
    _add_rectangle(msp, ((0, 0), (400, 0), (400, 600), (0, 600)), layer=CUT)
    msp.add_lwpolyline(
        [
            (40, 40),
            (40, 540),
            (55, 540),
            (55, 40),
            (70, 40),
            (70, 540),
            (85, 540),
            (85, 40),
        ],
        dxfattribs={"layer": "Liner"},
        close=False,
    )
    msp.add_line((360, 40), (360, 560), dxfattribs={"layer": "Rear Groove"})
    msp.add_lwpolyline(
        [
            (80, 200),
            (180, 200),
            (180, 320),
            (90, 320),
            (90, 210),
            (170, 210),
            (170, 310),
        ],
        dxfattribs={"layer": "Handle Recess"},
        close=False,
    )
    return doc


def _layer0_designer_plan_doc():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _add_rectangle(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer="0")
    _add_rectangle(msp, ((100, 100), (500, 100), (500, 700), (100, 700)), layer="0")
    _add_rectangle(msp, ((480, 80), (510, 80), (510, 720), (480, 720)), layer="0")
    _add_rectangle(msp, ((220, 280), (300, 280), (300, 480), (220, 480)), layer="0")
    _add_rectangle(msp, ((90, 90), (510, 90), (510, 710), (90, 710)), layer="along")
    msp.add_lwpolyline(
        [(-10, 100), (-7, 100)],
        dxfattribs={"layer": "PIECES"},
        close=False,
    )
    msp.add_lwpolyline(
        [
            (485, 120),
            (485, 680),
            (500, 680),
            (500, 120),
            (492, 120),
            (492, 680),
        ],
        dxfattribs={"layer": "Liner"},
        close=False,
    )
    msp.add_line((360, 140), (360, 660), dxfattribs={"layer": "Rear Groove"})
    msp.add_lwpolyline(
        [
            (230, 300),
            (290, 300),
            (290, 460),
            (235, 460),
            (235, 310),
        ],
        dxfattribs={"layer": "Handle Recess"},
        close=False,
    )
    return doc


def _sheet_outline_with_layer0_cuts_doc():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _add_rectangle(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer=SHEET)
    _add_rectangle(msp, ((40, 40), (440, 40), (440, 640), (40, 640)), layer="0")
    return doc


def _test1_reference_plan_doc():
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    _add_rectangle(
        msp,
        (
            (-1913.388905491083, -1159.857173812828),
            (-1895.388905491083, -1159.857173812828),
            (-1895.388905491083, -250.8571738128285),
            (-1913.388905491083, -250.8571738128285),
        ),
        layer="0",
    )
    msp.add_lwpolyline(
        [
            (-1897.888905491083, -253.3571738128285),
            (-1897.888905491083, -1157.357173812828),
            (-1902.888905491083, -1157.357173812828),
            (-1902.888905491083, -253.3571738128285),
            (-1905.888905491083, -253.3571738128285),
            (-1905.888905491083, -1157.357173812828),
            (-1910.888905491083, -1157.357173812828),
            (-1910.888905491083, -253.3571738128285),
        ],
        dxfattribs={"layer": "Liner"},
        close=False,
    )
    _add_rectangle(
        msp,
        (
            (-2175.388905491084, -1154.857173812828),
            (-1845.388905491083, -1154.857173812828),
            (-1845.388905491083, -255.8571738128285),
            (-2175.388905491083, -255.8571738128285),
        ),
        layer="0",
    )
    _add_rectangle(
        msp,
        (
            (-2177.888905491084, -1157.357173812828),
            (-1842.888905491084, -1157.357173812828),
            (-1842.888905491084, -253.3571738128285),
            (-2177.888905491084, -253.3571738128285),
        ),
        layer="along",
    )
    msp.add_lwpolyline(
        [(-1877.496405917391, -253.3571738128285), (-1880.496405917391, -253.3571738128285)],
        dxfattribs={"layer": "PIECES"},
        close=False,
    )
    _add_rectangle(
        msp,
        (
            (-2087.388905491085, -804.8571738128284),
            (-2125.388905491083, -804.8571738128284),
            (-2125.388905491083, -605.8571738128285),
            (-2087.388905491083, -605.8571738128285),
        ),
        layer="0",
    )
    msp.add_lwpolyline(
        [
            (-2122.888905491083, -800.0178066647112),
            (-2122.888905491083, -802.3571738128284),
            (-2089.888905491083, -802.3571738128284),
            (-2089.888905491083, -608.3571738128283),
            (-2122.888905491083, -608.3571738128283),
            (-2122.888905491083, -797.3571738128285),
            (-2094.888905491083, -797.3571738128285),
            (-2094.888905491083, -613.3571738128283),
            (-2117.888905491083, -613.3571738128283),
            (-2117.888905491083, -792.3571738128283),
            (-2099.888905491083, -792.3571738128283),
            (-2099.888905491083, -618.3571738128285),
            (-2112.888905491083, -618.3571738128285),
            (-2112.888905491083, -787.3571738128283),
            (-2107.888905491083, -787.3571738128283),
            (-2107.888905491083, -623.3571738128285),
            (-2104.888905491083, -623.3571738128285),
            (-2104.888905491083, -787.3571738128283),
            (-2107.115390854058, -787.3571738128283),
        ],
        dxfattribs={"layer": "Handle Recess"},
        close=False,
    )
    msp.add_line(
        (-1865.388905491083, -1157.357173812828),
        (-1865.388905491083, -253.3571738128285),
        dxfattribs={"layer": "Rear Groove"},
    )
    _add_rectangle(
        msp,
        (
            (-3052.888905491084, 1272.642826187172),
            (-3052.888905491084, -1167.357173812828),
            (-1832.888905491083, -1167.357173812828),
            (-1832.888905491083, 1272.642826187171),
        ),
        layer="0",
    )
    return doc


class TestExtraDxfOverlayImport(unittest.TestCase):
    def tearDown(self) -> None:
        for path in getattr(self, "paths", []):
            Path(path).unlink(missing_ok=True)

    def _parse(self, doc, order):
        path = _write_dxf(doc)
        self.paths = getattr(self, "paths", []) + [path]
        with patch.object(dxf_import_service.frappe, "get_site_path", return_value=path):
            return dxf_import_service.parse_production_dxf(
                "/private/files/extra-overlay.dxf",
                order,
            )

    def test_reader_includes_overlay_layers_without_breaking_sheet_and_cut(self) -> None:
        doc = _extra_plan_doc()
        path = _write_dxf(doc)
        self.paths = getattr(self, "paths", []) + [path]
        result = read_dxf_geometry(
            path,
            relevant_layers={SHEET, CUT, *EXTRA_OVERLAY_LAYER_NAMES},
        )
        layers = {row["layer"] for row in result["segments"]}
        self.assertEqual(layers, {SHEET, CUT, "LINER"})
        self.assertIn("LINER", result["diagnostics"]["relevant_layers"])
        self.assertIn(SHEET, result["diagnostics"]["relevant_layers"])
        self.assertIn(CUT, result["diagnostics"]["relevant_layers"])

    def test_extra_with_liner_overlay_is_accepted_and_not_counted_as_a_piece(self) -> None:
        snapshot = self._parse(_extra_plan_doc(), _order(piece_type="Extra", extra_liner=1))
        pieces = snapshot["sheets"][0]["pieces"]
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0]["piece_type"], "Extra")
        overlays = pieces[0]["overlays"]
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0]["kind"], "liner")
        self.assertEqual(overlays[0]["layer"], "Liner")
        self.assertGreaterEqual(len(overlays[0]["geometry"]["path"]), 2)
        self.assertNotIn("holes", overlays[0]["geometry"])
        self.assertNotIn("overlays", pieces[0]["geometry"])

    def test_reference_open_liner_groove_and_handle_marks_are_accepted(self) -> None:
        snapshot = self._parse(
            _reference_style_extra_plan_doc(),
            _order(
                piece_type="Extra",
                extra_liner=1,
                extra_back_groove=1,
                extra_recessed_handle_cutout=1,
            ),
        )
        overlays = snapshot["sheets"][0]["pieces"][0]["overlays"]
        by_kind = {item["kind"]: item for item in overlays}
        self.assertEqual(set(by_kind), {"liner", "back_groove", "recessed_handle_cutout"})
        self.assertFalse(by_kind["liner"]["geometry"]["closed"])
        self.assertGreaterEqual(len(by_kind["liner"]["geometry"]["path"]), 8)
        self.assertEqual(len(by_kind["back_groove"]["geometry"]["path"]), 2)
        self.assertFalse(by_kind["back_groove"]["geometry"]["closed"])
        self.assertFalse(by_kind["recessed_handle_cutout"]["geometry"]["closed"])
        self.assertEqual(len(snapshot["sheets"][0]["pieces"]), 1)

    def test_layer0_designer_file_is_accepted_without_canonical_cut_layers(self) -> None:
        snapshot = self._parse(
            _layer0_designer_plan_doc(),
            _order(
                piece_type="Extra",
                extra_liner=1,
                extra_back_groove=1,
                extra_recessed_handle_cutout=1,
            ),
        )
        pieces = snapshot["sheets"][0]["pieces"]
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0]["piece_type"], "Extra")
        by_kind = {item["kind"]: item for item in pieces[0]["overlays"]}
        self.assertEqual(set(by_kind), {"liner", "back_groove", "recessed_handle_cutout"})

    def test_sheet_outline_with_doors_on_layer0_is_accepted_as_cut_path(self) -> None:
        snapshot = self._parse(
            _sheet_outline_with_layer0_cuts_doc(),
            _order(piece_type="Regular"),
        )
        pieces = snapshot["sheets"][0]["pieces"]
        self.assertEqual(len(pieces), 1)
        self.assertAlmostEqual(pieces[0]["w"], 40.0)
        self.assertAlmostEqual(pieces[0]["h"], 60.0)

    def test_test1_reference_geometry_on_layer0_is_accepted(self) -> None:
        snapshot = self._parse(
            _test1_reference_plan_doc(),
            _order(
                piece_type="Extra",
                extra_liner=1,
                extra_back_groove=1,
                extra_recessed_handle_cutout=1,
                cut_width_cm=33,
                cut_length_cm=89.9,
            ),
        )
        pieces = snapshot["sheets"][0]["pieces"]
        self.assertEqual(len(pieces), 1)
        by_kind = {item["kind"]: item for item in pieces[0]["overlays"]}
        self.assertEqual(set(by_kind), {"liner", "back_groove", "recessed_handle_cutout"})
        self.assertGreaterEqual(len(by_kind["recessed_handle_cutout"]["geometry"]["path"]), 18)
        self.assertFalse(by_kind["recessed_handle_cutout"]["geometry"]["closed"])

    def test_handle_recess_self_approaching_polyline_stays_one_open_mark(self) -> None:
        points = [
            (80.0, 200.0),
            (80.0, 200.8),
            (180.0, 200.8),
            (180.0, 320.0),
            (90.0, 320.0),
            (90.0, 201.5),
            (170.0, 201.5),
            (170.0, 310.0),
            (100.0, 310.0),
            (100.0, 202.2),
        ]
        rows = []
        for start, end in zip(points, points[1:]):
            rows.append(
                {
                    "layer": "HANDLE RECESS",
                    "entity_type": "LWPOLYLINE",
                    "entity_id": 7,
                    "closed": False,
                    "start": start,
                    "end": end,
                }
            )
        paths, errors = dxf_import_service._overlay_source_paths(rows, "Handle Recess")
        self.assertEqual(errors, ())
        self.assertEqual(len(paths), 1)
        path_points, closed = paths[0]
        self.assertFalse(closed)
        self.assertEqual(len(path_points), len(points))
        overlays = dxf_import_service._collect_extra_overlay_candidates(rows)
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0].kind, "recessed_handle_cutout")
        self.assertFalse(overlays[0].closed)

    def test_canonical_cut_layers_ignore_extra_closed_boxes_on_layer0(self) -> None:
        doc = _extra_plan_doc()
        msp = doc.modelspace()
        _add_rectangle(msp, ((700, 100), (1100, 100), (1100, 700), (700, 700)), layer="0")
        snapshot = self._parse(doc, _order(piece_type="Extra", extra_liner=1))
        self.assertEqual(len(snapshot["sheets"][0]["pieces"]), 1)

    def test_extra_without_drawn_overlay_is_still_accepted(self) -> None:
        snapshot = self._parse(
            _extra_plan_doc(overlay_layer=None),
            _order(piece_type="Extra", extra_liner=1),
        )
        self.assertEqual(len(snapshot["sheets"][0]["pieces"]), 1)
        self.assertNotIn("overlays", snapshot["sheets"][0]["pieces"][0])

    def test_liner_overlay_on_regular_is_rejected(self) -> None:
        with self.assertRaises(DxfImportError) as exc_info:
            self._parse(_extra_plan_doc(), _order(piece_type="Regular"))
        message = str(exc_info.exception)
        self.assertIn("Liner", message)
        self.assertIn("Extra", message)

    def test_overlay_on_extra_without_matching_addon_is_rejected(self) -> None:
        with self.assertRaises(DxfImportError) as exc_info:
            self._parse(
                _extra_plan_doc(),
                _order(piece_type="Extra", extra_back_groove=1),
            )
        self.assertIn("الخانة المطابقة", str(exc_info.exception))
        self.assertIn("احفظ الطلب", str(exc_info.exception))

    def test_strict_import_proxy_keeps_liner_checkbox_when_accepting_overlay(self) -> None:
        from decimal import Decimal

        from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
            OrderPieceCutSpec,
        )
        from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
            _proxy_order,
        )

        live_order = _order(piece_type="Extra", extra_liner=1)
        spec = OrderPieceCutSpec(
            row_index=1,
            finished_width_cm=Decimal("40"),
            finished_length_cm=Decimal("60"),
            cut_width_cm=Decimal("40"),
            cut_length_cm=Decimal("60"),
            width_deduction_mm=Decimal("0"),
            length_deduction_mm=Decimal("0"),
            allow_rotation=0,
            piece_type="Extra",
            qty=1,
            side_profiles=(),
        )
        proxy = _proxy_order(live_order, [spec], SimpleNamespace(kerf_mm=5))
        snapshot = self._parse(_extra_plan_doc(), proxy)
        overlays = snapshot["sheets"][0]["pieces"][0]["overlays"]
        self.assertEqual(overlays[0]["kind"], "liner")

    def test_overlay_left_on_cut_path_is_still_rejected(self) -> None:
        with self.assertRaises(DxfImportError) as exc_info:
            self._parse(
                _extra_plan_doc(
                    overlay_layer=None,
                    overlay_on_cut_path=True,
                    overlay_points=((300, 100), (500, 100), (500, 300), (300, 300)),
                ),
                _order(piece_type="Extra", extra_liner=1),
            )
        message = str(exc_info.exception)
        self.assertTrue(
            "لا يمكن مطابقة محيطات CUT_PATH" in message
            or "تعذر تحديد القطع والفتحات" in message
            or "تتداخلان" in message
            or "تتداخل" in message
        )

    def test_missing_sheet_and_cut_layers_explain_canonical_roles(self) -> None:
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        _add_rectangle(msp, ((0, 0), (1220, 0), (1220, 2440), (0, 2440)), layer="NOTES")
        _add_rectangle(msp, ((40, 40), (180, 40), (180, 160), (40, 160)), layer=LINER)
        with self.assertRaises(DxfImportError) as exc_info:
            self._parse(doc, _order(piece_type="Extra", extra_liner=1))
        message = str(exc_info.exception)
        self.assertIn(SHEET, message)
        self.assertIn(CUT, message)
        self.assertIn("NOTES", message)
        self.assertIn("أي طبقة غير SHEET_OUTLINE وCUT_PATH", message)
        self.assertIn("طبقات علامات Extra (Liner)", message)
        self.assertNotIn("PIECES", message)
        self.assertNotIn("ALONG", message)


if __name__ == "__main__":
    unittest.main()
