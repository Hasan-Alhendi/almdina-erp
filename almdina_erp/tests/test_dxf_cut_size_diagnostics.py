from __future__ import annotations

import unittest
from types import SimpleNamespace

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.services.dxf_import_service import (
    DxfImportError,
    _legacy_expected_piece_match,
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
    @staticmethod
    def _order(*pieces: tuple[float, float, int]):
        return SimpleNamespace(
            kerf_mm=0,
            pieces=[
                SimpleNamespace(
                    cut_width_cm=width / 10,
                    cut_length_cm=height / 10,
                    width_cm=width / 10,
                    length_cm=height / 10,
                    qty=1,
                    allow_rotation=rotation,
                    piece_type="Regular",
                    extra_full_door_double=0,
                )
                for width, height, rotation in pieces
            ],
        )

    def test_direct_orientation_is_accepted_when_rotation_is_forbidden(self) -> None:
        _resolve_cut_topology([_rect(592, 285)], self._order((592, 285, 0)))

    def test_forbidden_rotation_has_precise_diagnostic(self) -> None:
        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology([_rect(285, 592)], self._order((592, 285, 0)))
        message = str(exc_info.exception)
        self.assertIn("الدرفة 1", message)
        self.assertIn("28.5 × 59.2 سم", message)
        self.assertIn("59.2 × 28.5 سم", message)
        self.assertIn("مدوّرة 90°", message)
        self.assertIn("التدوير غير مسموح", message)
        self.assertNotIn("لا يمكن مطابقة محيطات CUT_PATH", message)
        self.assertNotIn("قريب من مقاس القص", message)

    def test_near_rotated_size_is_not_forbidden_rotation(self) -> None:
        order = self._order((592, 285, 0))
        for actual_width, actual_height in ((286, 591), (285, 591)):
            with self.subTest(actual=(actual_width, actual_height)):
                with self.assertRaises(DxfImportError) as exc_info:
                    _resolve_cut_topology(
                        [_rect(actual_width, actual_height)], order
                    )
                self.assertIn(
                    "لا يمكن مطابقة محيطات CUT_PATH",
                    str(exc_info.exception),
                )
                self.assertNotIn("مدوّرة 90°", str(exc_info.exception))
                self.assertNotIn("التدوير غير مسموح", str(exc_info.exception))

    def test_allowed_rotation_is_accepted(self) -> None:
        _resolve_cut_topology([_rect(285, 592)], self._order((592, 285, 1)))

    def test_translation_does_not_change_piece_matching(self) -> None:
        translated = {
            "points": [(1200, 800), (1792, 800), (1792, 1085), (1200, 1085)],
            "closed": True,
            "branched": False,
        }
        _resolve_cut_topology([translated], self._order((592, 285, 0)))

    def test_exact_rotation_proof_ignores_float_representation_noise(self) -> None:
        noisy = {
            "points": [
                (0.1, 0.1),
                (285.1000000000001, 0.1),
                (285.1000000000001, 592.1),
                (0.1, 592.1),
            ],
            "closed": True,
            "branched": False,
        }
        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology([noisy], self._order((592, 285, 0)))
        self.assertIn("مدوّرة 90°", str(exc_info.exception))

    def test_legacy_forbidden_rotation_requires_exact_swapped_dimensions(self) -> None:
        expected = [{
            "width_cm": 59.2,
            "length_cm": 28.5,
            "allow_rotation": False,
            "label": "9",
        }]

        exact = _legacy_expected_piece_match(
            width_cm=28.5, height_cm=59.2,
            expected=expected, unmatched_indexes=[0],
        )
        self.assertIs(exact[0], None)
        self.assertIs(exact[2], expected[0])

        for width_cm, height_cm in ((28.6, 59.1), (28.5, 59.1)):
            with self.subTest(width_cm=width_cm, height_cm=height_cm):
                near = _legacy_expected_piece_match(
                    width_cm=width_cm, height_cm=height_cm,
                    expected=expected, unmatched_indexes=[0],
                )
                self.assertIsNone(near[2])

        allowed = [{**expected[0], "allow_rotation": True}]
        rotated = _legacy_expected_piece_match(
            width_cm=28.5, height_cm=59.2,
            expected=allowed, unmatched_indexes=[0],
        )
        self.assertEqual(rotated, (0, True, None))

        direct = _legacy_expected_piece_match(
            width_cm=59.2, height_cm=28.5,
            expected=expected, unmatched_indexes=[0],
        )
        self.assertEqual(direct, (0, False, None))

    def test_real_size_mismatch_remains_generic(self) -> None:
        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology([_rect(570, 285)], self._order((592, 285, 0)))
        self.assertIn("لا يمكن مطابقة محيطات CUT_PATH", str(exc_info.exception))
        self.assertNotIn("مدوّرة 90°", str(exc_info.exception))

    def test_repeated_dimensions_do_not_guess_forbidden_rotation(self) -> None:
        order = self._order((592, 285, 0), (592, 285, 0))
        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology([_rect(592, 285), _rect(285, 592)], order)
        self.assertIn("لا يمكن مطابقة محيطات CUT_PATH", str(exc_info.exception))
        self.assertNotIn("مدوّرة 90°", str(exc_info.exception))

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
