"""Regression: exclusive OFFCUT doors import with modern GEOMETRY files."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import cutter_center_segments
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CUT_OPEN,
    CUT_SELF_INTERSECTION,
    KERF_VIOLATION,
    MATERIAL_OVERLAP,
    MIXED_RESOURCE_SOURCE,
    OFFCUT_IDENTITY_MISMATCH,
    PIECE_MISSING,
)
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError

SHEET = dxf_import_service.SHEET_OUTLINE_LAYER
CUT = dxf_import_service.CUT_PATH_LAYER
GEOMETRY = dxf_import_service.GEOMETRY_LAYER
OFFCUT = dxf_import_service.OFFCUT_LAYER


def _write_dxf(doc) -> str:
    handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    handle.close()
    doc.saveas(handle.name)
    return handle.name


def _add_rectangle(msp, points, *, layer: str) -> None:
    corners = tuple(points)
    for start, end in zip(corners, (*corners[1:], corners[0])):
        msp.add_line(start, end, dxfattribs={"layer": layer})


def _rect(x: float, y: float, width: float, height: float):
    return (
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
    )


def _piece(
    *,
    cut_width_cm: float,
    cut_length_cm: float,
    piece_instance_id: str = "door-1",
    qty: int = 1,
):
    return SimpleNamespace(
        piece_instance_id=piece_instance_id,
        qty=qty,
        piece_type="Regular",
        width_cm=cut_width_cm,
        length_cm=cut_length_cm,
        cut_width_cm=cut_width_cm,
        cut_length_cm=cut_length_cm,
        allow_rotation=0,
        edge_long_left=0,
        edge_long_right=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_long_thickness_mm=0,
        edge_width_thickness_mm=0,
        edge_break=0,
        extra_liner=0,
        extra_back_groove=0,
        extra_full_door_double=0,
        extra_recessed_handle_cutout=0,
        extra_double=0,
        liner_reference_side="",
        liner_offset_cm=0,
        liner_width_cm=0,
        liner_start_cm=0,
        liner_length_cm=0,
    )


def _order(pieces):
    return SimpleNamespace(
        name="DCO-OFFCUT-GEOM",
        pieces=pieces,
        trim_margin_mm=0,
        board_width_cm=122,
        board_length_cm=244,
        full_board_width_mm=1220,
        full_board_length_mm=2440,
        kerf_mm=5,
        default_edge_type="",
    )


def _parse(path: str, order):
    with (
        patch.object(dxf_import_service.frappe, "get_site_path", return_value=path),
        patch.object(dxf_import_service, "_", lambda message, *_args, **_kwargs: message),
    ):
        return dxf_import_service.parse_production_dxf(path, order)


def _two_sheet_doc(layers=("SHEET_OUTLINE", "CUT_PATH", "GEOMETRY", "OFFCUT", "TEXT")):
    doc = ezdxf.new("R2010")
    for name in layers:
        doc.layers.add(name)
    msp = doc.modelspace()
    _add_rectangle(msp, _rect(0, 0, 1220, 2440), layer=SHEET)
    _add_rectangle(msp, _rect(1400, 0, 1220, 2440), layer=SHEET)
    return doc, msp


class TestDxfOffcutGeometryImport(unittest.TestCase):
    def tearDown(self) -> None:
        for path in getattr(self, "paths", []):
            Path(path).unlink(missing_ok=True)

    def _run(self, doc, order):
        path = _write_dxf(doc)
        self.paths = getattr(self, "paths", []) + [path]
        return _parse(path, order)

    def test_geometry_plus_exclusive_offcut_extracts_all_doors(self):
        """GEOMETRY doors on board 1 + exclusive OFFCUT on board 2."""
        doc, msp = _two_sheet_doc()
        for door in (
            _rect(20, 20, 300, 400),
            _rect(340, 20, 250, 350),
        ):
            _add_rectangle(msp, door, layer=GEOMETRY)
        _add_rectangle(msp, _rect(1420, 20, 398, 618), layer=OFFCUT)

        order = _order(
            [
                _piece(piece_instance_id="g1", cut_width_cm=30, cut_length_cm=40),
                _piece(piece_instance_id="g2", cut_width_cm=25, cut_length_cm=35),
                _piece(piece_instance_id="o1", cut_width_cm=39.8, cut_length_cm=61.8),
            ]
        )
        snapshot = self._run(doc, order)
        pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
        self.assertEqual(len(pieces), 3)
        offcut_pieces = [
            piece
            for piece in pieces
            if str(piece.get("resource_kind") or "").upper() == "OFFCUT"
        ]
        self.assertEqual(len(offcut_pieces), 1)
        self.assertEqual(
            {(round(piece["w"], 1), round(piece["h"], 1)) for piece in offcut_pieces},
            {(39.8, 61.8)},
        )
        full_board = [
            piece
            for piece in pieces
            if str(piece.get("resource_kind") or "FULL_BOARD").upper() != "OFFCUT"
        ]
        self.assertEqual(len(full_board), 2)
        sheet_kinds = {
            int(sheet["sheet_no"]): sheet["resource_kind"] for sheet in snapshot["sheets"]
        }
        self.assertIn("OFFCUT", sheet_kinds.values())
        self.assertIn("FULL_BOARD", sheet_kinds.values())
        self.assertEqual(snapshot["validation"]["is_valid"], True)

    def test_dual_layer_contour_classifies_once_without_duplication(self):
        doc, msp = _two_sheet_doc()
        door = _rect(20, 20, 400, 600)
        _add_rectangle(msp, door, layer=GEOMETRY)
        _add_rectangle(msp, door, layer=OFFCUT)

        order = _order([_piece(cut_width_cm=40, cut_length_cm=60)])
        snapshot = self._run(doc, order)
        pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0]["resource_kind"], "OFFCUT")
        self.assertEqual(pieces[0]["offcut_source_party"], "UNASSIGNED")
        self.assertEqual(pieces[0]["offcut_execution_party"], "UNASSIGNED")
        self.assertAlmostEqual(snapshot["used_area_m2"], 0.4 * 0.6, places=6)
        self.assertEqual(snapshot["sheets"][0]["resource_kind"], "OFFCUT")

    def test_legacy_cut_path_plus_offcut_without_geometry_unchanged(self):
        doc, msp = _two_sheet_doc(layers=("SHEET_OUTLINE", "CUT_PATH", "OFFCUT", "TEXT"))
        _add_rectangle(msp, _rect(20, 20, 300, 400), layer=CUT)
        _add_rectangle(msp, _rect(1420, 20, 200, 250), layer=OFFCUT)

        order = _order(
            [
                _piece(piece_instance_id="c1", cut_width_cm=30, cut_length_cm=40),
                _piece(piece_instance_id="o1", cut_width_cm=20, cut_length_cm=25),
            ]
        )
        snapshot = self._run(doc, order)
        pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
        self.assertEqual(len(pieces), 2)
        self.assertEqual(snapshot["saw_center_status"], "Legacy")
        offcut_count = sum(
            1
            for piece in pieces
            if str(piece.get("resource_kind") or "").upper() == "OFFCUT"
        )
        self.assertEqual(offcut_count, 1)

    def test_invalid_offcut_contour_is_rejected(self):
        doc, msp = _two_sheet_doc()
        _add_rectangle(msp, _rect(20, 20, 300, 400), layer=GEOMETRY)
        # Open OFFCUT path on the remnant board: not a finished door contour.
        msp.add_line((1420, 20), (1818, 20), dxfattribs={"layer": OFFCUT})
        msp.add_line((1818, 20), (1818, 638), dxfattribs={"layer": OFFCUT})
        msp.add_line((1818, 638), (1420, 638), dxfattribs={"layer": OFFCUT})

        order = _order(
            [
                _piece(piece_instance_id="g1", cut_width_cm=30, cut_length_cm=40),
                _piece(piece_instance_id="o1", cut_width_cm=39.8, cut_length_cm=61.8),
            ]
        )
        with self.assertRaises(DxfImportError) as raised:
            self._run(doc, order)
        codes = set(raised.exception.codes)
        self.assertTrue(codes & {CUT_OPEN, PIECE_MISSING, OFFCUT_IDENTITY_MISMATCH})

    def test_overlapping_offcut_is_rejected(self):
        doc, msp = _two_sheet_doc()
        _add_rectangle(msp, _rect(20, 20, 400, 600), layer=GEOMETRY)
        # Distinct size that still overlaps the geometry door footprint.
        _add_rectangle(msp, _rect(40, 40, 398, 618), layer=OFFCUT)

        order = _order(
            [
                _piece(piece_instance_id="g1", cut_width_cm=40, cut_length_cm=60),
                _piece(piece_instance_id="o1", cut_width_cm=39.8, cut_length_cm=61.8),
            ]
        )
        with self.assertRaises(DxfImportError) as raised:
            self._run(doc, order)
        codes = set(raised.exception.codes)
        self.assertTrue(
            codes
            & {
                MATERIAL_OVERLAP,
                KERF_VIOLATION,
                CUT_SELF_INTERSECTION,
                MIXED_RESOURCE_SOURCE,
                OFFCUT_IDENTITY_MISMATCH,
            },
            msg=f"unexpected rejection codes: {sorted(codes)}",
        )

    def test_ordinary_geometry_only_import_unaffected(self):
        doc, msp = _two_sheet_doc()
        _add_rectangle(msp, _rect(20, 20, 500, 500), layer=GEOMETRY)
        order = _order([_piece(cut_width_cm=50, cut_length_cm=50)])
        snapshot = self._run(doc, order)
        pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
        self.assertEqual(len(pieces), 1)
        self.assertEqual(
            str(pieces[0].get("resource_kind") or "FULL_BOARD").upper(),
            "FULL_BOARD",
        )
        self.assertEqual(snapshot["sheets"][0]["resource_kind"], "FULL_BOARD")
        self.assertEqual(snapshot["saw_center_status"], "Absent")

    def test_exclusive_offcut_does_not_invalidate_geometry_saw_centers(self):
        doc, msp = _two_sheet_doc()
        geometry_door = _rect(20, 20, 300, 400)
        _add_rectangle(msp, geometry_door, layer=GEOMETRY)
        _add_rectangle(msp, _rect(1420, 20, 398, 618), layer=OFFCUT)
        centers = cutter_center_segments(
            [(geometry_door, ())],
            2.5,
            board=(0.0, 0.0, 1220.0, 2440.0),
        )
        for start, end in centers:
            msp.add_line(start, end, dxfattribs={"layer": CUT})

        order = _order(
            [
                _piece(piece_instance_id="g1", cut_width_cm=30, cut_length_cm=40),
                _piece(piece_instance_id="o1", cut_width_cm=39.8, cut_length_cm=61.8),
            ]
        )
        snapshot = self._run(doc, order)
        pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
        self.assertEqual(len(pieces), 2)
        self.assertEqual(snapshot["saw_center_status"], "Present")
        self.assertEqual(
            sum(
                1
                for piece in pieces
                if str(piece.get("resource_kind") or "").upper() == "OFFCUT"
            ),
            1,
        )

    def test_fifteen_door_geometry_offcut_mix_matches_reported_regression(self):
        """2 boards / 12 GEOMETRY + 3 exclusive OFFCUT → 15 extracted doors."""
        doc, msp = _two_sheet_doc()
        geometry_specs = [
            (20, 20, 300, 400),
            (340, 20, 300, 400),
            (660, 20, 300, 400),
            (20, 440, 300, 400),
            (340, 440, 300, 400),
            (660, 440, 300, 400),
            (20, 860, 300, 400),
            (340, 860, 300, 400),
            (660, 860, 300, 400),
            (20, 1280, 300, 400),
            (340, 1280, 300, 400),
            (660, 1280, 300, 400),
        ]
        offcut_specs = [
            (1420, 20, 398, 618),
            (1840, 20, 638, 618),
            (1420, 660, 593, 618),
        ]
        for x, y, w, h in geometry_specs:
            _add_rectangle(msp, _rect(x, y, w, h), layer=GEOMETRY)
        for x, y, w, h in offcut_specs:
            _add_rectangle(msp, _rect(x, y, w, h), layer=OFFCUT)

        order_pieces = [
            _piece(piece_instance_id=f"g{index}", cut_width_cm=30, cut_length_cm=40)
            for index in range(1, 13)
        ]
        order_pieces.extend(
            [
                _piece(piece_instance_id="o1", cut_width_cm=39.8, cut_length_cm=61.8),
                _piece(piece_instance_id="o2", cut_width_cm=63.8, cut_length_cm=61.8),
                _piece(piece_instance_id="o3", cut_width_cm=59.3, cut_length_cm=61.8),
            ]
        )
        snapshot = self._run(doc, _order(order_pieces))
        pieces = [piece for sheet in snapshot["sheets"] for piece in sheet["pieces"]]
        self.assertEqual(len(pieces), 15)
        offcut_pieces = [
            piece
            for piece in pieces
            if str(piece.get("resource_kind") or "").upper() == "OFFCUT"
        ]
        self.assertEqual(len(offcut_pieces), 3)
        self.assertEqual(
            sorted(
                (round(piece["w"], 1), round(piece["h"], 1)) for piece in offcut_pieces
            ),
            [(39.8, 61.8), (59.3, 61.8), (63.8, 61.8)],
        )


class TestOffcutOnlySegmentHelper(unittest.TestCase):
    def test_helper_skips_geometry_matching_offcut_and_keeps_exclusive(self):
        geometry = _rect(0, 0, 100, 200)
        exclusive = _rect(150, 0, 80, 90)
        geometry_segments = list(zip(geometry, (*geometry[1:], geometry[0])))
        offcut_segments = [
            *zip(geometry, (*geometry[1:], geometry[0])),
            *zip(exclusive, (*exclusive[1:], exclusive[0])),
        ]
        geometry_polygons = dxf_import_service._closed_polygons_from_segments(
            geometry_segments
        )
        kept = dxf_import_service._offcut_only_cut_segments(
            offcut_segments,
            geometry_polygons,
        )
        kept_polygons = dxf_import_service._closed_polygons_from_segments(kept)
        self.assertEqual(len(kept_polygons), 1)
        self.assertTrue(
            dxf_import_service._same_polygon_geometry(
                kept_polygons[0],
                exclusive,
                tolerance=dxf_import_service.GEOMETRY_TOLERANCE_MM,
            )
        )


if __name__ == "__main__":
    unittest.main()
