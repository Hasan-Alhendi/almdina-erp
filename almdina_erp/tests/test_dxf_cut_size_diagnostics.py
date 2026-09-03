from __future__ import annotations

import unittest
from types import SimpleNamespace

from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
    _resolve_cut_topology,
)
from almdina_erp.almdina_erp.services.piece_cut_dimension_service import (
    OrderPieceCutSpec,
)
from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
    _with_persisted_cut_context,
)
from decimal import Decimal


def _rect(width_mm: float, height_mm: float) -> dict:
    return {
        "points": [
            (0.0, 0.0),
            (width_mm, 0.0),
            (width_mm, height_mm),
            (0.0, height_mm),
        ],
        "closed": True,
        "branched": False,
    }


class TestDxfCutSizeDiagnostics(unittest.TestCase):
    def test_topology_mismatch_lists_dxf_sizes_and_near_miss(self) -> None:
        order = SimpleNamespace(
            kerf_mm=0,
            pieces=[
                SimpleNamespace(
                    cut_width_cm=29.9,
                    cut_length_cm=89.8,
                    width_cm=30,
                    length_cm=90,
                    qty=1,
                    allow_rotation=1,
                    piece_type="Regular",
                    extra_full_door_double=0,
                ),
                SimpleNamespace(
                    cut_width_cm=74.6,
                    cut_length_cm=29.9,
                    width_cm=74.6,
                    length_cm=30,
                    qty=1,
                    allow_rotation=1,
                    piece_type="Regular",
                    extra_full_door_double=0,
                ),
            ],
        )

        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology(
                [
                    _rect(299.0, 898.0),
                    _rect(289.0, 746.0),
                ],
                order,
            )

        message = str(exc_info.exception)
        self.assertIn("مقاسات DXF", message)
        self.assertIn("28.9 × 74.6", message)
        self.assertIn("مقاسات القص المطلوبة", message)
        self.assertIn("74.6 × 29.9", message)
        self.assertIn("قريب من مقاس القص", message)

    def test_strict_context_keeps_original_dxf_size_and_appends_cut_specs(self) -> None:
        original = DxfImportError(
            "القطعة رقم 2 أبعادها 28.9 × 74.6 سم ولا تطابق أي قطعة متبقية في الطلب ضمن سماحية ±2 مم."
        )
        annotated = _with_persisted_cut_context(
            original,
            [
                OrderPieceCutSpec(
                    row_index=1,
                    finished_width_cm=Decimal("74.6"),
                    finished_length_cm=Decimal("30"),
                    cut_width_cm=Decimal("74.6"),
                    cut_length_cm=Decimal("29.9"),
                    width_deduction_mm=Decimal("0"),
                    length_deduction_mm=Decimal("1"),
                    allow_rotation=1,
                    piece_type="Regular",
                    qty=1,
                    side_profiles=(),
                )
            ],
        )

        text = str(annotated)
        self.assertIn("28.9 × 74.6", text)
        self.assertIn("مقاسات القص التصنيعية المحفوظة", text)
        self.assertIn("لا توجد سماحية لتغيير مقاس الدرفة", text)

    def test_strict_context_does_not_replace_cut_path_inventory(self) -> None:
        original = DxfImportError(
            "لا يمكن مطابقة محيطات CUT_PATH المغلقة مع قطع الطلب المطلوبة. مقاسات DXF: 28.9 × 74.6 سم."
        )
        annotated = _with_persisted_cut_context(original, [])
        self.assertIs(annotated, original)


if __name__ == "__main__":
    unittest.main()
