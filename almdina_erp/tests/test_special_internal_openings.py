"""Special doors may own internal through-cut openings.

Regular stays a rectangle with no opening. Glass stays one rectangular
opening that matches its margins. A rectangular Special is valid only after
it owns at least one opening. Identity is the order row, not contour order.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cnc.operational_file import catalog_sheet
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    _materialize_piece,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import rederive_outline
from almdina_erp.almdina_erp.domain.cutting.board_editor_transform import apply_local_flip_h
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    cutter_center_paths,
    internal_center_ring,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import point_in_polygon
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    parse_geometry_mm,
    serialize_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import topology_error_to_issue
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    ContourCandidate,
    DxfTopologyError,
    ExpectedPieceEvidence,
    PartGeometry,
    resolve_contour_ownership,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import (
    validate_glass_dxf_opening,
)
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issue
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError


def _rect(x1, y1, x2, y2):
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def _circle(cx, cy, radius, count=16):
    return tuple(
        (
            cx + radius * math.cos(2 * math.pi * index / count),
            cy + radius * math.sin(2 * math.pi * index / count),
        )
        for index in range(count)
    )


def _ellipse(cx, cy, rx, ry, count=16):
    return tuple(
        (
            cx + rx * math.cos(2 * math.pi * index / count),
            cy + ry * math.sin(2 * math.pi * index / count),
        )
        for index in range(count)
    )


def _chamfer(x, y, width, height):
    return (
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x + 40, y + height),
        (x, y + height - 40),
    )


def _candidate(key, polygon):
    return ContourCandidate(key=key, polygon=polygon)


def _resolve(contours, expected, **kwargs):
    return resolve_contour_ownership(
        contours,
        expected,
        dimension_tolerance=2,
        geometry_tolerance=0.25,
        **kwargs,
    )


def _regular(width=400, height=600):
    return ExpectedPieceEvidence(width, height, False, piece_type="Regular")


def _special(width=400, height=600, **kwargs):
    return ExpectedPieceEvidence(width, height, False, piece_type="Special", **kwargs)


def _glass(width=400, height=600, margin=50):
    return ExpectedPieceEvidence(
        width,
        height,
        False,
        piece_type="Glass",
        is_glass=True,
        glass_margin_mm=margin,
        deduct_edge_thickness=False,
    )


def _glass_hole(margin=50, width=400, height=600):
    return _rect(margin, margin, width - margin, height - margin)


def _part(topology, key):
    return next(part for part in topology.parts if part.contour_key == key)


class SpecialOpeningIdentityTest(unittest.TestCase):
    def test_accepted_regular_glass_and_special_geometry(self):
        regular = _resolve((_candidate(1, _rect(0, 0, 400, 600)),), (_regular(),))
        self.assertEqual(_part(regular, 1).geometry.holes, ())

        glass = _resolve(
            (
                _candidate(1, _rect(0, 0, 400, 600)),
                _candidate(2, _glass_hole()),
            ),
            (_glass(),),
        )
        self.assertEqual(len(_part(glass, 1).geometry.holes), 1)

        circular = _resolve(
            (
                _candidate(1, _rect(0, 0, 400, 600)),
                _candidate(2, _circle(200, 300, 80)),
            ),
            (_special(),),
        )
        self.assertEqual(len(_part(circular, 1).geometry.holes), 1)

        rectangular_opening = _resolve(
            (
                _candidate(1, _rect(0, 0, 400, 600)),
                _candidate(2, _rect(80, 80, 320, 520)),
            ),
            (_special(),),
        )
        self.assertEqual(len(_part(rectangular_opening, 1).geometry.holes), 1)

        mixed = _resolve(
            (
                _candidate(1, _rect(0, 0, 400, 600)),
                _candidate(2, _rect(40, 40, 140, 160)),
                _candidate(3, _circle(280, 180, 40)),
                _candidate(4, _ellipse(250, 420, 50, 30)),
            ),
            (_special(),),
        )
        self.assertEqual(len(_part(mixed, 1).geometry.holes), 3)

        plain_shape = _resolve((_candidate(1, _chamfer(0, 0, 400, 600)),), (_special(),))
        self.assertEqual(_part(plain_shape, 1).geometry.holes, ())

        shaped_with_hole = _resolve(
            (
                _candidate(1, _chamfer(0, 0, 400, 600)),
                _candidate(2, _circle(180, 200, 40)),
            ),
            (_special(),),
        )
        self.assertEqual(len(_part(shaped_with_hole, 1).geometry.holes), 1)

    def test_rejected_geometry(self):
        with self.assertRaises(DxfTopologyError) as plain_special:
            _resolve((_candidate(1, _rect(0, 0, 400, 600)),), (_special(),))
        self.assertEqual(plain_special.exception.code, "SPECIAL_OUTLINE_IS_RECTANGLE")

        with self.assertRaises(DxfTopologyError) as regular_hole:
            _resolve(
                (
                    _candidate(1, _rect(0, 0, 400, 600)),
                    _candidate(2, _circle(200, 300, 40)),
                ),
                (_regular(),),
            )
        self.assertEqual(regular_hole.exception.code, "REGULAR_OPENING_UNEXPECTED")

        circular_glass = validate_glass_dxf_opening(
            outer=_rect(0, 0, 400, 600),
            holes=(_circle(200, 300, 80),),
            piece_type="Glass",
            margin_mm=50,
            tolerance=0.25,
            deduct_edge_thickness=False,
        )
        self.assertNotEqual(circular_glass.code, "")

        multiple = validate_glass_dxf_opening(
            outer=_rect(0, 0, 400, 600),
            holes=(_glass_hole(), _rect(60, 60, 120, 120)),
            piece_type="Glass",
            margin_mm=50,
            tolerance=0.25,
            deduct_edge_thickness=False,
        )
        self.assertEqual(multiple.code, "GLASS_MULTIPLE_OPENINGS")

        wrong_margin = validate_glass_dxf_opening(
            outer=_rect(0, 0, 400, 600),
            holes=(_rect(80, 80, 320, 520),),
            piece_type="Glass",
            margin_mm=50,
            tolerance=0.25,
            deduct_edge_thickness=False,
        )
        self.assertNotEqual(wrong_margin.code, "")

        special_ignores_margins = validate_glass_dxf_opening(
            outer=_rect(0, 0, 400, 600),
            holes=(_circle(200, 300, 40),),
            piece_type="Special",
            margin_mm=50,
            tolerance=0.25,
        )
        self.assertFalse(special_ignores_margins.code)

        invalid_holes = (
            ((20, 20), (80, 80), (80, 20), (20, 80)),  # self-intersection
            _rect(20, 20, 120, 120),  # touches the second hole on y=120
            ((10, 10), (80, 10)),  # not a closed area
        )
        for polygon in invalid_holes:
            with self.subTest(points=len(polygon)):
                with self.assertRaises(DxfTopologyError):
                    _resolve(
                        (
                            _candidate(1, _rect(0, 0, 400, 600)),
                            _candidate(2, polygon),
                            _candidate(3, _rect(20, 120, 120, 220)),
                        ),
                        (_special(),),
                    )

        with self.assertRaises(DxfTopologyError):
            _resolve(
                (
                    _candidate(1, _rect(0, 0, 400, 600)),
                    _candidate(2, _rect(500, 0, 560, 40)),
                ),
                (_special(),),
            )

        self.assertFalse(
            dxf_import_service._opening_accepts_cutter(
                _rect(0, 0, 400, 600),
                _rect(100, 100, 104, 104),
                2.5,
            )
        )

    def test_mixed_orders_require_evidence_for_glass_and_special(self):
        regular_outer = _candidate(1, _rect(0, 0, 400, 600))
        glass_outer = _candidate(2, _rect(0, 700, 400, 1300))
        glass_hole = _candidate(3, _rect(50, 750, 350, 1250))
        special_outer = _candidate(4, _rect(500, 0, 900, 600))
        special_hole = _candidate(5, _circle(700, 300, 70))
        mixed = _resolve(
            (regular_outer, glass_outer, glass_hole, special_outer, special_hole),
            (_regular(), _glass(), _special()),
        )
        self.assertEqual(_part(mixed, 1).geometry.holes, ())
        self.assertEqual(len(_part(mixed, 2).geometry.holes), 1)
        self.assertEqual(len(_part(mixed, 4).geometry.holes), 1)
        self.assertEqual(_part(mixed, 2).expected_piece_index, 1)
        self.assertEqual(_part(mixed, 4).expected_piece_index, 2)

        matching = _candidate(10, _rect(0, 0, 400, 600))
        matching_hole = _candidate(11, _glass_hole())
        other = _candidate(12, _rect(500, 0, 900, 600))
        other_hole = _candidate(13, _rect(580, 80, 820, 520))
        unique = _resolve(
            (other, other_hole, matching, matching_hole),
            (_glass(), _special()),
        )
        self.assertEqual(_part(unique, 10).expected_piece_index, 0)
        self.assertEqual(_part(unique, 12).expected_piece_index, 1)

        twin_a = _candidate(20, _rect(0, 0, 400, 600))
        twin_a_hole = _candidate(21, _glass_hole())
        twin_b = _candidate(22, _rect(500, 0, 900, 600))
        twin_b_hole = _candidate(23, _rect(550, 50, 850, 550))
        with self.assertRaises(DxfTopologyError) as ambiguous:
            _resolve(
                (twin_b, twin_b_hole, twin_a, twin_a_hole),
                (_glass(), _special()),
            )
        self.assertEqual(ambiguous.exception.code, "PIECE_IDENTITY_AMBIGUOUS")
        issue = topology_error_to_issue(ambiguous.exception)
        presented = present_issue(issue)
        self.assertNotIn("20", presented.problem)
        self.assertNotIn("22", presented.problem)

        locked = _resolve(
            (twin_b, twin_b_hole, twin_a, twin_a_hole),
            (_glass(), _special()),
            identity_locks={20: 0},
        )
        self.assertEqual(_part(locked, 20).expected_piece_index, 0)
        self.assertEqual(_part(locked, 22).expected_piece_index, 1)

        signed = _resolve(
            (twin_b, twin_b_hole, twin_a, twin_a_hole),
            (
                _glass(),
                _special(addon_signature=frozenset({"liner"})),
            ),
            contour_signatures={22: frozenset({"liner"})},
        )
        self.assertEqual(_part(signed, 22).expected_piece_index, 1)
        self.assertEqual(_part(signed, 20).expected_piece_index, 0)

        shuffled = _resolve(
            (special_hole, regular_outer, glass_hole, special_outer, glass_outer),
            (_special(), _regular(), _glass()),
        )
        self.assertEqual(_part(shuffled, 1).expected_piece_index, 1)
        self.assertEqual(_part(shuffled, 2).expected_piece_index, 2)
        self.assertEqual(_part(shuffled, 4).expected_piece_index, 0)

        nested = _resolve(
            (
                _candidate(1, _rect(0, 0, 900, 2100)),
                _candidate(2, _rect(150, 300, 750, 1800)),
                _candidate(3, _rect(220, 450, 420, 650)),
            ),
            (
                _glass(width=900, height=2100, margin=150),
                ExpectedPieceEvidence(200, 200, False, piece_type="Regular"),
            ),
        )
        self.assertEqual(len(nested.parts), 2)
        self.assertEqual(_part(nested, 1).hole_contour_keys, (2,))
        self.assertEqual(_part(nested, 3).geometry.holes, ())

        with self.assertRaises(DxfTopologyError) as addon_only:
            _resolve(
                (_candidate(1, _rect(0, 0, 400, 600)),),
                (_special(addon_signature=frozenset({"liner"})),),
            )
        self.assertEqual(addon_only.exception.code, "SPECIAL_OUTLINE_IS_RECTANGLE")

    def test_geometry_round_trip_editor_and_cutter_order(self):
        outer = _rect(0, 0, 400, 600)
        holes = (_rect(40, 40, 140, 160), _circle(280, 300, 50))
        stored = serialize_geometry_mm(PartGeometry(outer=outer, holes=holes))
        restored = parse_geometry_mm(stored)
        self.assertEqual(len(restored.holes), 2)

        posed_rings = [
            [[point[0] + 10, point[1] + 20] for point in ring]
            for ring in holes
        ]
        materialized = _materialize_piece(
            posed={
                "piece_instance_id": "pi-special",
                "piece_id": 7,
                "label": "S",
                "local_x_mm": 10,
                "local_y_mm": 20,
                "outline_mm": [[point[0] + 10, point[1] + 20] for point in outer],
                "opening_rings_mm": posed_rings,
                "rotation_deg": 0,
            },
            source_piece={
                "piece_type": "Special",
                "geometry": stored,
                "geometry_source": "cnc_raw_rect",
                "w": 40,
                "h": 60,
            },
            trusted_piece={"piece_type": "Special", "width_mm": 400, "length_mm": 600},
        )
        self.assertEqual(len(materialized["geometry"]["holes"]), 2)

        piece = {
            "outline_mm": [list(point) for point in outer],
            "base_outline_mm": [list(point) for point in outer],
            "pivot_mm": {"x": 200, "y": 300},
            "rotation_deg": 90,
            "opening_rings_mm": [list(map(list, ring)) for ring in holes],
        }
        rederive_outline(piece)
        self.assertEqual(len(piece["opening_rings_mm"]), 2)
        self.assertNotEqual(piece["opening_rings_mm"][0][0], list(holes[0][0]))
        before_flip = [point[:] for point in piece["opening_rings_mm"][0]]
        apply_local_flip_h(piece)
        self.assertEqual(len(piece["opening_rings_mm"]), 2)
        self.assertNotEqual(piece["opening_rings_mm"][0], before_flip)

        paths = cutter_center_paths([(outer, list(holes))], 2.5)
        self.assertGreaterEqual(len(paths), 3)
        self.assertTrue(all(path.closed for path in paths))
        self.assertTrue(point_in_polygon(paths[0].points[0], holes[0], 0.25))
        center = internal_center_ring(outer, holes[0], 2.5)
        self.assertIsNotNone(center)
        self.assertTrue(point_in_polygon(center[0], holes[0], 0.25))

        catalog = catalog_sheet(
            1,
            [{
                "piece_instance_id": "pi-special",
                "sheet_no": 1,
                "extra_liner": 0,
                "extra_back_groove": 0,
                "extra_recessed_handle_cutout": 0,
                "geometry": stored,
            }],
        )
        cut_keys = [path.path_key for path in catalog.paths if path.operation_key == "cut_path"]
        self.assertTrue(any(":hole:" in key for key in cut_keys))
        self.assertLess(
            min(index for index, key in enumerate(cut_keys) if ":hole:" in key),
            next(index for index, key in enumerate(cut_keys) if key.endswith(":outer")),
        )


class SpecialOpeningImportTest(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            Path(path).unlink(missing_ok=True)

    def _parse(self, doc, order):
        handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        handle.close()
        doc.saveas(handle.name)
        self.paths.append(handle.name)
        with patch.object(dxf_import_service.frappe, "get_site_path", return_value=handle.name):
            return dxf_import_service.parse_production_dxf("/private/files/special.dxf", order)

    def _order(self, pieces):
        return SimpleNamespace(
            trim_margin_mm=0,
            board_width_cm=122,
            board_length_cm=244,
            full_board_width_mm=1220,
            full_board_length_mm=2440,
            kerf_mm=5,
            pieces=pieces,
        )

    def _piece(self, **overrides):
        values = {
            "cut_width_cm": 40,
            "cut_length_cm": 60,
            "width_cm": 40,
            "length_cm": 60,
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

    def _doc(self):
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        corners = ((0, 0), (1220, 0), (1220, 2440), (0, 2440))
        for start, end in zip(corners, (*corners[1:], corners[0])):
            msp.add_line(start, end, dxfattribs={"layer": "SHEET_OUTLINE"})
        return doc, msp

    def _lines(self, msp, polygon, layer="CUT_PATH"):
        corners = tuple(polygon)
        for start, end in zip(corners, (*corners[1:], corners[0])):
            msp.add_line(start, end, dxfattribs={"layer": layer})

    def test_import_keeps_special_openings_and_rejects_plain_rectangle(self):
        doc, msp = self._doc()
        self._lines(msp, _rect(0, 0, 400, 600))
        self._lines(msp, _circle(200, 300, 80))
        snapshot = self._parse(doc, self._order([self._piece()]))
        piece = snapshot["sheets"][0]["pieces"][0]
        self.assertEqual(piece["piece_type"], "Special")
        self.assertEqual(len(piece["geometry"]["holes"]), 1)

        again, again_msp = self._doc()
        self._lines(again_msp, piece["geometry"]["outer"])
        for hole in piece["geometry"]["holes"]:
            self._lines(again_msp, hole)
        reimported = self._parse(again, self._order([self._piece()]))
        self.assertEqual(len(reimported["sheets"][0]["pieces"][0]["geometry"]["holes"]), 1)

        bare, bare_msp = self._doc()
        self._lines(bare_msp, _rect(0, 0, 400, 600))
        self._lines(bare_msp, ((80, 120), (80, 480)), layer="Liner")
        with self.assertRaises(DxfImportError) as error:
            self._parse(bare, self._order([self._piece(extra_liner=1)]))
        self.assertTrue(any(item.code == "SPECIAL_OUTLINE_IS_RECTANGLE" for item in error.exception.issues))

        tiny, tiny_msp = self._doc()
        self._lines(tiny_msp, _rect(0, 0, 400, 600))
        self._lines(tiny_msp, _rect(180, 280, 184, 284))
        with self.assertRaises(DxfImportError) as uncut:
            self._parse(tiny, self._order([self._piece()]))
        self.assertTrue(any(item.code == "OPENING_UNMANUFACTURABLE" for item in uncut.exception.issues))
