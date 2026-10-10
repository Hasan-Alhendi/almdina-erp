from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    ContourCandidate,
    ExpectedPieceEvidence,
    resolve_contour_ownership,
)
from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
    _resolve_cut_topology,
)


FIXTURE = Path(__file__).parent / "fixtures" / "dxf_181_golden_baseline.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rect(width_mm: float, height_mm: float, *, x_mm: float = 0.0) -> dict:
    return {
        "points": [
            (x_mm, 0.0),
            (x_mm + width_mm, 0.0),
            (x_mm + width_mm, height_mm),
            (x_mm, height_mm),
        ],
        "closed": True,
        "branched": False,
    }


def _order_from_fixture(data: dict):
    rows = []
    for piece in data["scenario"]["order_pieces"]:
        rows.append(
            SimpleNamespace(
                cut_width_cm=piece["cut_width_cm"],
                cut_length_cm=piece["cut_length_cm"],
                width_cm=piece["cut_width_cm"],
                length_cm=piece["cut_length_cm"],
                qty=piece["qty"],
                allow_rotation=int(piece["allow_rotation"]),
                piece_type=piece["piece_type"],
                extra_full_door_double=0,
            )
        )
    return SimpleNamespace(kerf_mm=0, pieces=rows)


class TestAlmadina181DxfGoldenBaseline(unittest.TestCase):
    def test_fixture_captures_anonymized_source_counts_and_keeps_offcuts_separate(self):
        data = _fixture()
        source = data["source_evidence"]
        scenario = data["scenario"]

        self.assertEqual(source["source_dxf_entity_counts_by_layer"]["CUT_PATH"], 47)
        self.assertEqual(source["source_dxf_entity_counts_by_layer"]["OFFCUT"], 2)
        self.assertEqual(source["source_pdf_order_row_count"], 12)
        self.assertEqual(source["source_pdf_piece_copy_count"], 49)
        self.assertEqual(len(scenario["offcut_resources"]), 2)
        self.assertTrue(
            all(item["resource_kind"] == "OFFCUT" for item in scenario["offcut_resources"])
        )
        self.assertEqual(
            sum(piece["qty"] for piece in scenario["order_pieces"]),
            len(scenario["cut_path_bboxes_mm"]),
        )

    def test_current_baseline_reports_generic_inventory_mismatch_for_multiple_rotations(self):
        data = _fixture()
        order = _order_from_fixture(data)
        contours = [_rect(*bbox) for bbox in data["scenario"]["cut_path_bboxes_mm"]]

        with self.assertRaises(DxfImportError) as raised:
            _resolve_cut_topology(contours, order)

        self.assertEqual(raised.exception.codes, ["EXPECTED_PIECE_MISMATCH"])
        diagnostic = raised.exception.issues[0]
        self.assertEqual(diagnostic.target.kind, "order")
        self.assertEqual(diagnostic.params["topology_code"], "EXPECTED_PIECE_MISMATCH")
        self.assertEqual(diagnostic.params["actual_count"], 5)
        self.assertEqual(diagnostic.params["expected_count"], 5)
        self.assertEqual(diagnostic.params["missing_count"], 4)
        self.assertEqual(diagnostic.params["extra_count"], 4)
        self.assertNotIn("source_piece_no", diagnostic.params)

    @unittest.expectedFailure
    def test_multiple_forbidden_rotations_keep_piece_copy_identity_and_dimensions(self):
        data = _fixture()
        order = _order_from_fixture(data)
        contours = [_rect(*bbox) for bbox in data["scenario"]["cut_path_bboxes_mm"]]

        with self.assertRaises(DxfImportError) as raised:
            _resolve_cut_topology(contours, order)

        error = raised.exception
        self.assertEqual(error.codes, ["FORBIDDEN_ROTATION"] * 4)
        targets = [issue.target for issue in error.issues]
        self.assertEqual(
            [(target.source_piece_no, target.copy_no) for target in targets],
            [(1, 1), (2, 1), (2, 2), (3, 1)],
        )
        self.assertEqual(
            [issue.params["actual_width_cm"] for issue in error.issues],
            [89.9, 61.0, 61.0, 60.5],
        )
        self.assertEqual(
            [issue.params["actual_height_cm"] for issue in error.issues],
            [29.9, 29.9, 29.9, 29.9],
        )

    def test_allowed_rotation_is_accepted_with_same_cut_dimensions(self):
        topology = resolve_contour_ownership(
            [ContourCandidate(key=1, polygon=((0, 0), (285, 0), (285, 592), (0, 592)))],
            [ExpectedPieceEvidence(width=592, height=285, allow_rotation=True)],
            dimension_tolerance=2.0,
        )
        self.assertEqual(topology.parts[0].expected_piece_index, 0)

    def test_special_outline_and_nested_hole_keep_geometry_ownership(self):
        contours = [
            ContourCandidate(
                key=1,
                polygon=((0, 0), (300, 0), (300, 250), (180, 250), (180, 400), (0, 400)),
            ),
            ContourCandidate(key=2, polygon=((30, 30), (80, 30), (80, 80), (30, 80))),
        ]
        topology = resolve_contour_ownership(
            contours,
            [ExpectedPieceEvidence(width=300, height=400, allow_rotation=False, arbitrary_outline=True)],
            dimension_tolerance=2.0,
        )

        self.assertEqual(topology.parts[0].expected_piece_index, 0)
        self.assertEqual(topology.parts[0].hole_contour_keys, (2,))


if __name__ == "__main__":
    unittest.main()
