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
    _validate_topology_candidate_dimensions,
    _with_persisted_cut_context,
)
from decimal import Decimal


def _present_error(error: DxfImportError) -> str:
    from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issues_as_strings

    return "\n".join(present_issues_as_strings(error.issues))


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
        error = exc_info.exception
        self.assertIn("FORBIDDEN_ROTATION", error.codes)
        message = _present_error(error)
        self.assertIn("الدرفة 1", message)
        self.assertIn("28.5", message)
        self.assertIn("59.2", message)
        self.assertIn("مدوّرة", message)
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
                message = _present_error(exc_info.exception)
                self.assertTrue(
                    "PIECE_MISSING" in exc_info.exception.codes
                    or "EXPECTED_PIECE_MISMATCH" in exc_info.exception.codes
                )
                self.assertNotIn("مدوّرة 90°", message)
                self.assertNotIn("التدوير غير مسموح", message)

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
        self.assertIn("FORBIDDEN_ROTATION", exc_info.exception.codes)
        self.assertIn("مدوّرة", _present_error(exc_info.exception))

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

    @staticmethod
    def _strict_dimension_result(
        width_cm: float,
        length_cm: float,
        *,
        piece_type: str = "Special",
        allow_rotation: int = 0,
    ) -> tuple[bool | None, str | None]:
        spec = OrderPieceCutSpec(
            row_index=1,
            finished_width_cm=Decimal("30"),
            finished_length_cm=Decimal("40"),
            cut_width_cm=Decimal("30"),
            cut_length_cm=Decimal("40"),
            width_deduction_mm=Decimal("0"),
            length_deduction_mm=Decimal("0"),
            allow_rotation=allow_rotation,
            piece_type=piece_type,
            qty=1,
            side_profiles=(),
        )
        return _validate_topology_candidate_dimensions(
            {"w": width_cm, "h": length_cm},
            {"label": "1.1", "spec": spec},
        )

    def test_special_bbox_accepts_exact_and_one_sided_deductions_through_two_mm(self) -> None:
        for width_cm, length_cm in (
            (30.00, 40.00),
            (29.90, 40.00),
            (30.00, 39.90),
            (29.80, 40.00),
            (30.00, 39.80),
            (29.80, 39.80),
            (29.85, 39.90),
        ):
            with self.subTest(width_cm=width_cm, length_cm=length_cm):
                rotated, error = self._strict_dimension_result(width_cm, length_cm)
                self.assertIs(rotated, False)
                self.assertIsNone(error)

    def test_special_bbox_rejects_over_deduction_and_any_oversize(self) -> None:
        for width_cm, length_cm in (
            (29.799, 40.00),
            (30.00, 39.799),
            (29.79, 40.00),
            (30.00, 39.79),
            (30.01, 40.00),
            (30.00, 40.01),
        ):
            with self.subTest(width_cm=width_cm, length_cm=length_cm):
                rotated, error = self._strict_dimension_result(width_cm, length_cm)
                self.assertIsNone(rotated)
                self.assertIsNotNone(error)

    def test_special_two_mm_boundary_is_recognized_by_topology(self) -> None:
        order = self._order((300, 400, 0))
        order.pieces[0].piece_type = "Special"
        _resolve_cut_topology([_rect(298, 398)], order)

        rotated_order = self._order((300, 400, 1))
        rotated_order.pieces[0].piece_type = "Special"
        _resolve_cut_topology([_rect(398, 298)], rotated_order)

    def test_special_bbox_normalizes_float_noise_at_two_mm_boundary(self) -> None:
        rotated, error = self._strict_dimension_result(
            29.800000000000004,
            39.800000000000004,
        )
        self.assertIs(rotated, False)
        self.assertIsNone(error)

    def test_special_rotation_applies_same_deduction_rule_and_respects_permission(self) -> None:
        exact_allowed = self._strict_dimension_result(
            40, 30, allow_rotation=1,
        )
        self.assertEqual(exact_allowed, (True, None))

        deducted_allowed = self._strict_dimension_result(
            39.8, 29.8, allow_rotation=1,
        )
        self.assertEqual(deducted_allowed, (True, None))

        exact_forbidden = self._strict_dimension_result(
            40, 30, allow_rotation=0,
        )
        self.assertIsNone(exact_forbidden[0])
        self.assertIsNotNone(exact_forbidden[1])
        self.assertEqual(exact_forbidden[1].code, "FORBIDDEN_ROTATION")

    def test_non_special_piece_types_keep_exact_bbox_contract(self) -> None:
        for piece_type in ("Regular", "Clipped Corner", "L-Shaped Corner"):
            with self.subTest(piece_type=piece_type):
                rotated, error = self._strict_dimension_result(
                    29.9, 40, piece_type=piece_type,
                )
                self.assertIsNone(rotated)
                self.assertIsNotNone(error)

    def test_special_acceptance_keeps_actual_geometry_and_persisted_cut_size(self) -> None:
        from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
            _apply_strict_dimension_contract,
        )

        piece = {
            "label": "1.1",
            "source_piece_no": 1,
            "copy_no": 1,
            "piece_type": "Special",
            "w": 29.8,
            "h": 39.8,
            "rotated": False,
            "geometry": {"outer": [[0, 0], [29.8, 0], [29.8, 39.8]]},
        }
        snapshot = {"sheets": [{"pieces": [piece]}]}
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
        order = SimpleNamespace(pieces=[SimpleNamespace(
            piece_instance_id="piece:special-1",
            cut_width_cm=30,
            cut_length_cm=40,
            extra_full_door_double=0,
        )])

        errors = _apply_strict_dimension_contract(snapshot, [spec], order=order)

        self.assertEqual(errors, [])
        self.assertEqual((piece["w"], piece["h"]), (29.8, 39.8))
        self.assertEqual((piece["original_w"], piece["original_h"]), (30.0, 40.0))
        self.assertEqual((piece["cut_width_cm"], piece["cut_length_cm"]), (30.0, 40.0))
        self.assertEqual(piece["geometry"]["outer"][1], [29.8, 0])

    def test_real_size_mismatch_remains_generic(self) -> None:
        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology([_rect(570, 285)], self._order((592, 285, 0)))
        self.assertIn("EXPECTED_PIECE_MISMATCH", exc_info.exception.codes)
        self.assertIn("يوجد اختلاف في مقاسات القص", _present_error(exc_info.exception))
        self.assertNotIn("مدوّرة 90°", _present_error(exc_info.exception))

    def test_repeated_dimensions_report_group_without_copy_identity(self) -> None:
        order = self._order((592, 285, 0), (592, 285, 0))
        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology([_rect(592, 285), _rect(285, 592)], order)

        error = exc_info.exception
        rotations = [item for item in error.issues if item.code == "FORBIDDEN_ROTATION"]
        self.assertEqual(sum(item.params["rotation_count"] for item in rotations), 1)
        self.assertNotIn("EXPECTED_PIECE_MISMATCH", error.codes)
        self.assertTrue(all(item.target.source_piece_no is None for item in rotations))
        self.assertTrue(all(item.target.copy_no is None for item in rotations))
        candidate_rows = {
            row
            for item in rotations
            for row in (item.params.get("candidate_source_piece_nos") or ())
        }
        self.assertEqual(candidate_rows, {1, 2})

        from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
            CATEGORY_DIMENSIONS,
            DxfIssueTarget,
            FORBIDDEN_ROTATION,
            issue,
        )
        from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issue

        grouped = issue(
            FORBIDDEN_ROTATION,
            CATEGORY_DIMENSIONS,
            target=DxfIssueTarget(kind="order"),
            params={
                "rotation_count": 1,
                "candidate_source_piece_nos": [1, 2],
                "possible_measurements_cm": [{
                    "actual_width_cm": 28.5,
                    "actual_height_cm": 59.2,
                    "expected_width_cm": 59.2,
                    "expected_height_cm": 28.5,
                }],
                "identity_ambiguous": True,
            },
        )
        card = present_issue(grouped)
        self.assertIn("قطعة واحدة", card.problem)
        self.assertEqual(card.target, "الدرف المحتملة: 1، 2.")
        self.assertIn("28.5 × 59.2 سم", card.action)
        self.assertIn("59.2 × 28.5 سم", card.action)

    def test_large_duplicate_copy_set_has_deterministic_rotation_count(self) -> None:
        quantity = 80
        order = SimpleNamespace(
            kerf_mm=0,
            pieces=[SimpleNamespace(
                cut_width_cm=59.2,
                cut_length_cm=28.5,
                width_cm=59.2,
                length_cm=28.5,
                qty=quantity,
                allow_rotation=0,
                piece_type="Regular",
                extra_full_door_double=0,
            )],
        )
        contours = [
            _rect(
                592 if index < quantity // 2 else 285,
                285 if index < quantity // 2 else 592,
                x_mm=index * 700,
            )
            for index in range(quantity)
        ]

        results = []
        for _ in range(2):
            with self.assertRaises(DxfImportError) as exc_info:
                _resolve_cut_topology(contours, order)
            rotations = [
                item for item in exc_info.exception.issues
                if item.code == "FORBIDDEN_ROTATION"
            ]
            self.assertEqual(
                sum(item.params["rotation_count"] for item in rotations),
                quantity // 2,
            )
            self.assertTrue(all(item.target.copy_no is None for item in rotations))
            self.assertEqual(
                {
                    item.target.source_piece_no
                    or next(iter(item.params.get("candidate_source_piece_nos", [None])))
                    for item in rotations
                },
                {1},
            )
            normalized = []
            for item in rotations:
                measurements = item.params.get("possible_measurements_cm") or [{
                    "actual_width_cm": item.params.get("actual_width_cm"),
                    "actual_height_cm": item.params.get("actual_height_cm"),
                    "expected_width_cm": item.params.get("expected_width_cm"),
                    "expected_height_cm": item.params.get("expected_height_cm"),
                }]
                normalized.append((
                    item.params["rotation_count"],
                    tuple(item.params.get("candidate_source_piece_nos") or ()),
                    tuple(sorted(
                        tuple(measurement[field] for field in (
                            "actual_width_cm",
                            "actual_height_cm",
                            "expected_width_cm",
                            "expected_height_cm",
                        ))
                        for measurement in measurements
                    )),
                ))
            results.append(tuple(sorted(normalized)))

        self.assertEqual(results[0], results[1])

    def test_unrelated_duplicate_sizes_do_not_hide_piece_nine_rotation(self) -> None:
        dimensions = (
            (300, 400, 0), (300, 400, 0), (400, 500, 0),
            (210, 310, 0), (220, 330, 0), (230, 350, 0),
            (240, 370, 0), (250, 390, 0), (592, 285, 0),
        )
        contours = []
        x_mm = 0.0
        for index, (width, height, _) in enumerate(dimensions, start=1):
            actual_width, actual_height = (285, 592) if index == 9 else (width, height)
            contours.append(_rect(actual_width, actual_height, x_mm=x_mm))
            x_mm += actual_width + 20.0

        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology(contours, self._order(*dimensions))

        error = exc_info.exception
        self.assertEqual(error.codes, ["FORBIDDEN_ROTATION"])
        self.assertEqual(error.issues[0].target.source_piece_no, 9)
        from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issue

        card = present_issue(error.issues[0])
        self.assertEqual(card.problem, "الدرفة مدوّرة والتدوير غير مسموح.")
        self.assertEqual(card.target, "الدرفة 9.")
        self.assertEqual(card.action, "أعد اتجاه الدرفة إلى 59.2 × 28.5 سم.")
        message = _present_error(error)
        self.assertIn("الدرفة 9", message)
        self.assertIn("التدوير غير مسموح", message)
        self.assertIn("59.2 × 28.5 سم", message)
        for correct_size in ("30 × 40", "40 × 50", "21 × 31", "25 × 39"):
            self.assertNotIn(correct_size, message)

    def test_generic_mismatch_shows_only_residual_sizes(self) -> None:
        dimensions = ((300, 400, 0), (300, 400, 0), (420, 510, 0), (592, 285, 0))
        contours = []
        x_mm = 0.0
        for width, height in ((300, 400), (300, 400), (420, 510), (570, 280)):
            contours.append(_rect(width, height, x_mm=x_mm))
            x_mm += width + 20.0

        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology(contours, self._order(*dimensions))

        error = exc_info.exception
        self.assertEqual(error.codes, ["EXPECTED_PIECE_MISMATCH"])
        self.assertEqual(error.issues[0].params["extra_sizes"], ["57 × 28 سم"])
        self.assertEqual(error.issues[0].params["missing_sizes"], ["59.2 × 28.5 سم"])
        message = _present_error(error)
        self.assertIn("في الملف: 57 × 28 سم", message)
        self.assertIn("المطلوب: 59.2 × 28.5 سم", message)
        for correct_size in ("30 × 40", "42 × 51"):
            self.assertNotIn(correct_size, message)
        self.assertNotIn("الدرفة 4", message)

    def test_missing_piece_message_is_plain(self) -> None:
        order = self._order((649, 650, 0), (400, 399, 0))
        with self.assertRaises(DxfImportError) as exc_info:
            _resolve_cut_topology([_rect(649, 650)], order)
        self.assertIn("PIECE_MISSING", exc_info.exception.codes)
        message = _present_error(exc_info.exception)
        self.assertIn("درفة ناقصة", message)
        self.assertIn("يحتاج 2", message)
        self.assertIn("فيه 1", message)
        self.assertIn("40 × 39.9 سم", message)
        self.assertNotIn("لا يمكن مطابقة محيطات CUT_PATH", message)

    def test_topology_mismatch_shows_residual_sizes_and_near_miss(self) -> None:
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

        message = _present_error(exc_info.exception)
        self.assertIn("EXPECTED_PIECE_MISMATCH", exc_info.exception.codes)
        self.assertIn("يوجد اختلاف في مقاسات القص", message)
        self.assertIn("28.9 × 74.6", message)
        self.assertIn("74.6 × 29.9", message)
        self.assertNotIn("29.9 × 89.8", message)

    def test_strict_context_keeps_original_dxf_size_and_appends_cut_specs(self) -> None:
        from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
            CATEGORY_DIMENSIONS,
            CUT_SIZE_MISMATCH,
            PERSISTED_CUT_SPECS,
            contour_target,
            issue,
        )

        original = DxfImportError(
            issues=[
                issue(
                    CUT_SIZE_MISMATCH,
                    CATEGORY_DIMENSIONS,
                    target=contour_target(2),
                    params={
                        "actual_width_cm": 28.9,
                        "actual_height_cm": 74.6,
                    },
                )
            ]
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

        self.assertIn(PERSISTED_CUT_SPECS, annotated.codes)
        text = _present_error(annotated)
        self.assertIn("28.9", text)
        self.assertIn("74.6", text)
        self.assertIn("مقاسات القص المحفوظة", text)

    def test_strict_context_does_not_replace_cut_path_inventory(self) -> None:
        from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
            CATEGORY_IDENTITY,
            EXPECTED_PIECE_MISMATCH,
            issue,
        )

        original = DxfImportError(
            issues=[
                issue(
                    EXPECTED_PIECE_MISMATCH,
                    CATEGORY_IDENTITY,
                    params={"details": "مقاسات DXF: 28.9 × 74.6 سم."},
                )
            ]
        )
        annotated = _with_persisted_cut_context(original, [])
        self.assertIs(annotated, original)

    def test_strict_context_does_not_append_specs_for_missing_piece(self) -> None:
        from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
            CATEGORY_IDENTITY,
            PERSISTED_CUT_SPECS,
            PIECE_MISSING,
            DxfIssueTarget,
            issue,
        )

        original = DxfImportError(
            issues=[
                issue(
                    PIECE_MISSING,
                    CATEGORY_IDENTITY,
                    target=DxfIssueTarget(kind="order"),
                    params={
                        "actual_count": 1,
                        "expected_count": 2,
                        "missing_count": 1,
                        "missing_sizes": ["40 × 39.9 سم"],
                    },
                )
            ]
        )
        annotated = _with_persisted_cut_context(original, [])
        self.assertIs(annotated, original)
        self.assertNotIn(PERSISTED_CUT_SPECS, annotated.codes)


    def test_strict_context_omits_specs_for_identified_forbidden_rotation(self) -> None:
        from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
            CATEGORY_DIMENSIONS,
            FORBIDDEN_ROTATION,
            PERSISTED_CUT_SPECS,
            issue,
            piece_target,
        )

        original = DxfImportError(
            issues=[
                issue(
                    FORBIDDEN_ROTATION,
                    CATEGORY_DIMENSIONS,
                    target=piece_target(source_piece_no=9),
                    params={
                        "actual_width_mm": 285,
                        "actual_height_mm": 592,
                        "expected_width_mm": 592,
                        "expected_height_mm": 285,
                    },
                )
            ]
        )

        annotated = _with_persisted_cut_context(original, [])

        self.assertIs(annotated, original)
        self.assertEqual(annotated.codes, ["FORBIDDEN_ROTATION"])
        self.assertNotIn(PERSISTED_CUT_SPECS, annotated.codes)

    def test_strict_context_omits_specs_for_self_contained_grouped_rotation(self) -> None:
        from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
            CATEGORY_DIMENSIONS,
            DxfIssueTarget,
            FORBIDDEN_ROTATION,
            PERSISTED_CUT_SPECS,
            issue,
        )

        original = DxfImportError(
            issues=[
                issue(
                    FORBIDDEN_ROTATION,
                    CATEGORY_DIMENSIONS,
                    target=DxfIssueTarget(kind="order"),
                    params={
                        "rotation_count": 1,
                        "candidate_source_piece_nos": [1, 2],
                        "possible_measurements_cm": [{
                            "actual_width_cm": 28.5,
                            "actual_height_cm": 59.2,
                            "expected_width_cm": 59.2,
                            "expected_height_cm": 28.5,
                        }],
                        "identity_ambiguous": True,
                    },
                )
            ]
        )

        annotated = _with_persisted_cut_context(original, [])

        self.assertIs(annotated, original)
        self.assertEqual(annotated.codes, ["FORBIDDEN_ROTATION"])
        self.assertNotIn(PERSISTED_CUT_SPECS, annotated.codes)

    def test_strict_context_keeps_specs_for_forbidden_rotation_without_proof(self) -> None:
        from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
            CATEGORY_DIMENSIONS,
            FORBIDDEN_ROTATION,
            PERSISTED_CUT_SPECS,
            contour_target,
            issue,
        )

        original = DxfImportError(
            issues=[
                issue(
                    FORBIDDEN_ROTATION,
                    CATEGORY_DIMENSIONS,
                    target=contour_target(9),
                    params={
                        "actual_width_mm": 285,
                        "actual_height_mm": 592,
                        "expected_width_mm": 592,
                        "expected_height_mm": 285,
                    },
                )
            ]
        )

        annotated = _with_persisted_cut_context(original, [])

        self.assertIsNot(annotated, original)
        self.assertIn("FORBIDDEN_ROTATION", annotated.codes)
        self.assertIn(PERSISTED_CUT_SPECS, annotated.codes)


if __name__ == "__main__":
    unittest.main()
