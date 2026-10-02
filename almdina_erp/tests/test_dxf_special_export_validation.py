from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

import frappe

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import serialize_geometry_mm
from almdina_erp.almdina_erp.domain.cutting.manufacturing_requirements import (
    build_manufacturing_requirements,
)
from almdina_erp.almdina_erp.services.export_validation_service import (
    _expected_snapshot_pieces,
    _plan_to_export_snapshot,
    validate_cutting_plan_document,
)


def _saved_plan(
    *,
    piece_type: str,
    width_cm: float,
    length_cm: float,
    allow_rotation: bool = False,
    rotated: bool = False,
):
    width_mm = width_cm * 10
    length_mm = length_cm * 10
    geometry = serialize_geometry_mm(
        PartGeometry(
            outer=((0, 0), (width_mm, 0), (width_mm, length_mm), (0, length_mm)),
            holes=(),
        )
    )
    requirements = build_manufacturing_requirements(
        [
            {
                "label": "1.1",
                "source_piece_no": 1,
                "copy_no": 1,
                "cut_width_cm": 30,
                "cut_length_cm": 40,
                "allow_rotation": allow_rotation,
                "piece_type": piece_type,
            }
        ]
    )
    snapshot = {
        "manufacturing_requirements": requirements,
        "kerf_cm": 0,
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {
                        "id": 1,
                        "label": "1.1",
                        "geometry": geometry,
                    }
                ],
            }
        ],
        "unplaced": [],
    }
    piece = SimpleNamespace(
        sheet_no=1,
        piece_label="1.1",
        piece_id=1,
        source_piece_no=1,
        copy_no=1,
        x_mm=0,
        y_mm=0,
        width_mm=width_mm,
        height_mm=length_mm,
        original_width_cm=30,
        original_length_cm=40,
        rotated=int(rotated),
        edge_long_right=0,
        edge_long_left=0,
        edge_width_top=0,
        edge_width_bottom=0,
        edge_type="",
        notes="",
        piece_type=piece_type,
        clipped_corner_position="",
        clipped_corner_width_cm=0,
        clipped_corner_length_cm=0,
        special_shape_geometry_json="",
        edge_break=0,
    )
    source = SimpleNamespace(
        sheet_no=1,
        source_type="Full Board",
        remnant=None,
        board_item="",
        material="",
        color="",
        thickness_mm=0,
        full_width_mm=1000,
        full_length_mm=1000,
        usable_width_mm=1000,
        usable_length_mm=1000,
        source_area_m2=1,
    )
    plan = SimpleNamespace(
        plan_kind="Order",
        door_cutting_order="DCO-TEST",
        board_item="",
        snapshot_json=json.dumps(snapshot),
        kerf_mm=0,
        sources=[source],
        placed_pieces=[piece],
        engine_version="dxf-import-v2",
        method_key="custom_dxf",
        method_label="Uploaded DXF",
        full_board_width_mm=1000,
        full_board_length_mm=1000,
        usable_board_width_mm=1000,
        usable_board_length_mm=1000,
        trim_margin_mm=0,
        used_area_m2=width_cm * length_cm / 10000,
        total_source_area_m2=1,
        waste_area_m2=1 - width_cm * length_cm / 10000,
        required_boards=1,
    )
    order = SimpleNamespace(
        board_description="",
        board_material="",
        board_color="",
        board_thickness_mm=0,
    )
    return plan, order, piece, geometry


class TestSpecialExportValidation(unittest.TestCase):
    def _validate(self, **kwargs):
        plan, order, piece, geometry = _saved_plan(**kwargs)
        with patch.object(frappe, "get_doc", return_value=order, create=True):
            errors = validate_cutting_plan_document(plan)
        return plan, piece, geometry, errors

    def test_expected_snapshot_preserves_piece_type_from_manufacturing_requirements(self):
        plan, _, _, _ = _saved_plan(
            piece_type="Special", width_cm=30, length_cm=40
        )
        expected = _expected_snapshot_pieces(json.loads(plan.snapshot_json))
        self.assertEqual(expected["1.1"]["piece_type"], "Special")

    def test_special_export_accepts_exact_and_one_sided_deductions(self):
        accepted = (
            (30, 40),
            (29.9, 40),
            (30, 39.9),
            (29.8, 40),
            (30, 39.8),
            (29.8, 39.8),
        )
        for width_cm, length_cm in accepted:
            with self.subTest(width_cm=width_cm, length_cm=length_cm):
                _, _, _, errors = self._validate(
                    piece_type="Special",
                    width_cm=width_cm,
                    length_cm=length_cm,
                )
                self.assertEqual(errors, [])

    def test_special_export_rejects_over_deduction_and_oversize(self):
        rejected = ((29.799, 40), (30, 39.799), (30.001, 40), (30, 40.001))
        for width_cm, length_cm in rejected:
            with self.subTest(width_cm=width_cm, length_cm=length_cm):
                _, _, _, errors = self._validate(
                    piece_type="Special",
                    width_cm=width_cm,
                    length_cm=length_cm,
                )
                self.assertTrue(any("dimensions/orientation" in error for error in errors))

    def test_special_export_rotation_uses_same_rule_and_requires_matching_metadata(self):
        _, _, _, errors = self._validate(
            piece_type="Special",
            width_cm=40,
            length_cm=30,
            allow_rotation=True,
            rotated=True,
        )
        self.assertEqual(errors, [])

        _, _, _, errors = self._validate(
            piece_type="Special",
            width_cm=39.8,
            length_cm=29.8,
            allow_rotation=True,
            rotated=True,
        )
        self.assertEqual(errors, [])

        _, _, _, errors = self._validate(
            piece_type="Special",
            width_cm=39.8,
            length_cm=29.8,
            allow_rotation=False,
            rotated=True,
        )
        self.assertNotEqual(errors, [])
        self.assertTrue(any("rotated without permission" in error for error in errors))

        _, _, _, errors = self._validate(
            piece_type="Special",
            width_cm=39.8,
            length_cm=29.8,
            allow_rotation=True,
            rotated=False,
        )
        self.assertTrue(any("dimensions/orientation" in error for error in errors))

    def test_non_special_piece_types_remain_exact(self):
        for piece_type in ("Regular", "Extra", "Clipped Corner", "L-Shaped Corner"):
            with self.subTest(piece_type=piece_type):
                _, _, _, errors = self._validate(
                    piece_type=piece_type,
                    width_cm=29.9,
                    length_cm=40,
                )
                self.assertTrue(any("dimensions/orientation" in error for error in errors))

    def test_accepted_special_dimensions_survive_saved_plan_validation_and_export(self):
        from decimal import Decimal

        from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
            OrderPieceCutSpec,
        )
        from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
            _apply_strict_dimension_contract,
        )

        plan, piece, geometry, errors = self._validate(
            piece_type="Special",
            width_cm=29.8,
            length_cm=39.8,
        )
        self.assertEqual(errors, [])

        imported_piece = {
            "id": 1,
            "label": "1.1",
            "source_piece_no": 1,
            "copy_no": 1,
            "_expected_piece_index": 0,
            "piece_type": "Special",
            "w": 29.8,
            "h": 39.8,
            "geometry": geometry,
        }
        import_snapshot = {"sheets": [{"pieces": [imported_piece]}]}
        import_order = SimpleNamespace(
            pieces=[
                SimpleNamespace(
                    piece_instance_id="special:1",
                    cut_width_cm=30,
                    cut_length_cm=40,
                    extra_full_door_double=0,
                )
            ]
        )
        spec = OrderPieceCutSpec(
            row_index=1,
            finished_width_cm=Decimal("30"),
            finished_length_cm=Decimal("40"),
            cut_width_cm=Decimal("30"),
            cut_length_cm=Decimal("40"),
            width_deduction_mm=Decimal("0"),
            length_deduction_mm=Decimal("0"),
            allow_rotation=0,
            piece_type="Special",
            qty=1,
            side_profiles=(),
        )
        self.assertEqual(
            _apply_strict_dimension_contract(import_snapshot, [spec], order=import_order),
            [],
        )
        self.assertEqual((imported_piece["w"], imported_piece["h"]), (29.8, 39.8))
        self.assertEqual(
            (imported_piece["cut_width_cm"], imported_piece["cut_length_cm"]),
            (30.0, 40.0),
        )

        self.assertEqual((piece.width_mm, piece.height_mm), (298, 398))
        self.assertEqual((piece.original_width_cm, piece.original_length_cm), (30, 40))

        exported = _plan_to_export_snapshot(plan)
        exported_piece = exported["sheets"][0]["pieces"][0]
        self.assertEqual((exported_piece["w"], exported_piece["h"]), (29.8, 39.8))
        self.assertEqual((exported_piece["original_w"], exported_piece["original_h"]), (30, 40))
        self.assertEqual(exported_piece["geometry"], geometry)


if __name__ == "__main__":
    unittest.main()
