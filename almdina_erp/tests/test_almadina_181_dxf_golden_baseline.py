from __future__ import annotations

from collections import Counter
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

    def test_confirmed_rotations_do_not_degrade_to_generic_inventory_mismatch(self):
        data = _fixture()
        order = _order_from_fixture(data)
        contours = [_rect(*bbox) for bbox in data["scenario"]["cut_path_bboxes_mm"]]

        with self.assertRaises(DxfImportError) as raised:
            _resolve_cut_topology(contours, order)

        error = raised.exception
        self.assertIn("FORBIDDEN_ROTATION", error.codes)
        self.assertNotIn("EXPECTED_PIECE_MISMATCH", error.codes)
        self.assertEqual(
            sum(int(item.params.get("rotation_count", 1)) for item in error.issues),
            4,
        )

    def test_multiple_forbidden_rotations_report_rows_counts_and_dimensions(self):
        data = _fixture()
        order = _order_from_fixture(data)
        contours = [_rect(*bbox) for bbox in data["scenario"]["cut_path_bboxes_mm"]]

        with self.assertRaises(DxfImportError) as raised:
            _resolve_cut_topology(contours, order)

        rotations = [
            item for item in raised.exception.issues
            if item.code == "FORBIDDEN_ROTATION"
        ]
        row_counts = Counter()
        measurement_counts = Counter()
        for item in rotations:
            count = int(item.params.get("rotation_count", 1))
            source_piece_no = item.target.source_piece_no
            candidate_rows = tuple(item.params.get("candidate_source_piece_nos") or ())
            if source_piece_no is not None:
                row_counts[source_piece_no] += count
            elif len(candidate_rows) == 1:
                row_counts[candidate_rows[0]] += count

            measurements = item.params.get("possible_measurements_cm") or [{
                "actual_width_cm": item.params.get("actual_width_cm"),
                "actual_height_cm": item.params.get("actual_height_cm"),
                "expected_width_cm": item.params.get("expected_width_cm"),
                "expected_height_cm": item.params.get("expected_height_cm"),
            }]
            for measurement in measurements:
                measurement_counts[(
                    measurement["actual_width_cm"],
                    measurement["actual_height_cm"],
                    measurement["expected_width_cm"],
                    measurement["expected_height_cm"],
                )] += count if len(measurements) == 1 else 1

        # The two equal copies in row 2 are one grouped identity: assert their
        # quantity and dimensions, never a made-up 2.1/2.2 contour assignment.
        self.assertEqual(row_counts, Counter({1: 1, 2: 2, 3: 1}))
        row_2_issues = [
            item for item in rotations
            if item.target.source_piece_no == 2
            or item.params.get("candidate_source_piece_nos") == [2]
        ]
        self.assertTrue(row_2_issues)
        self.assertTrue(all(item.target.copy_no is None for item in row_2_issues))
        self.assertEqual(
            measurement_counts,
            Counter({
                (89.9, 29.9, 29.9, 89.9): 1,
                (61.0, 29.9, 29.9, 61.0): 2,
                (60.5, 29.9, 29.9, 60.5): 1,
            }),
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
