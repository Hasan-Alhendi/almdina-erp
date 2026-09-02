from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    PieceGeometry,
    PiecePolicyError,
    SpecialPrice,
    drawing_token,
    evaluate_special_shape,
    geometry_changed,
    pricing_basis_changed,
    protected_price_changed,
    reset_price_values,
    resolve_clipped_corner,
)


class TestOrderPiecePolicyDomain(unittest.TestCase):
    def test_drawing_token_is_stable_for_mapping_input(self) -> None:
        first = drawing_token({"elements": [], "version": 1})
        second = drawing_token({"version": 1, "elements": []})
        self.assertEqual(first, second)
        self.assertEqual(drawing_token("raw"), "raw")
        self.assertEqual(drawing_token(None), "")

    def test_clipped_corner_applies_defaults_and_validates_bounds(self) -> None:
        result = resolve_clipped_corner(
            position=None,
            piece_width_cm=100,
            piece_length_cm=200,
            cut_width_cm=0,
            cut_length_cm=0,
        )
        self.assertEqual(result.position, "Top Right")
        self.assertEqual(result.width_cm, 20)
        self.assertEqual(result.length_cm, 40)

        with self.assertRaisesRegex(PiecePolicyError, "clipped_corner_width_too_large"):
            resolve_clipped_corner(
                position="Top Left",
                piece_width_cm=100,
                piece_length_cm=200,
                cut_width_cm=100,
                cut_length_cm=10,
            )

    def test_geometry_change_policy_is_pure_and_explicit(self) -> None:
        old = PieceGeometry(width_cm=50, length_cm=100, qty=2)
        same = PieceGeometry(width_cm=50, length_cm=100, qty=2)
        changed = PieceGeometry(width_cm=51, length_cm=100, qty=2)

        self.assertFalse(geometry_changed(old, same, drawing_changed=False))
        self.assertTrue(geometry_changed(old, changed, drawing_changed=False))
        self.assertTrue(geometry_changed(old, same, drawing_changed=True))
        self.assertFalse(geometry_changed(None, changed, drawing_changed=True))

    def test_reviewed_price_basis_is_independent_from_drawing_and_edge_geometry(self) -> None:
        old = PieceGeometry(
            piece_type="Special",
            width_cm=90,
            length_cm=210,
            qty=2,
        )
        drawing_only = old
        edge_only = PieceGeometry(
            piece_type="Special",
            width_cm=90,
            length_cm=210,
            qty=2,
            edge_long_right=1,
            edge_long_left=1,
            edge_width_top=1,
            edge_width_bottom=1,
            edge_type="ABS",
        )
        other_geometry = PieceGeometry(
            piece_type="Special",
            width_cm=90,
            length_cm=210,
            qty=2,
            allow_rotation=1,
            clipped_corner_position="Top Right",
            clipped_corner_width_cm=12,
            clipped_corner_length_cm=18,
        )
        approved = SpecialPrice(
            unit_price_usd=125,
            status="Approved",
            note="reviewed",
            approved_by="accounts@example.com",
            approved_on="2026-08-20",
        )

        for label, current, drawing_changed, default_edge_changed in (
            ("drawing", drawing_only, True, False),
            ("piece edge", edge_only, False, False),
            ("default edge", old, False, True),
            ("other geometry", other_geometry, False, False),
        ):
            with self.subTest(label=label):
                decision = evaluate_special_shape(
                    old_geometry=old,
                    current_geometry=current,
                    old_price=approved,
                    current_price=approved,
                    drawing_changed=drawing_changed,
                    drawing_has_elements=True,
                    default_edge_changed=default_edge_changed,
                    approval_action=False,
                )
                self.assertFalse(decision.pricing_basis_changed)
                self.assertFalse(decision.reset_price)

        self.assertFalse(pricing_basis_changed(None, old))

    def test_only_piece_type_dimensions_and_quantity_change_reviewed_price_basis(self) -> None:
        old = PieceGeometry(
            piece_type="Special",
            width_cm=90,
            length_cm=210,
            qty=2,
        )
        cases = {
            "piece_type": PieceGeometry(
                piece_type="Regular",
                width_cm=90,
                length_cm=210,
                qty=2,
            ),
            "width_cm": PieceGeometry(
                piece_type="Special",
                width_cm=91,
                length_cm=210,
                qty=2,
            ),
            "length_cm": PieceGeometry(
                piece_type="Special",
                width_cm=90,
                length_cm=211,
                qty=2,
            ),
            "qty": PieceGeometry(
                piece_type="Special",
                width_cm=90,
                length_cm=210,
                qty=3,
            ),
        }

        for fieldname, current in cases.items():
            with self.subTest(fieldname=fieldname):
                self.assertTrue(pricing_basis_changed(old, current))

    def test_special_price_approval_does_not_require_drawing_documentation(self) -> None:
        service_path = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "services"
            / "special_shape_service.py"
        )
        source = service_path.read_text(encoding="utf-8")
        approval_source = source.split("def approve_special_piece_price", 1)[1]

        self.assertNotIn("piece.special_shape_status", approval_source)
        self.assertNotIn(
            "Document the special door shape before approving its price.",
            approval_source,
        )
        self.assertIn('if (piece.piece_type or "Regular") != "Special":', approval_source)
        self.assertIn("has_special_price_approval_permission", approval_source)

    def test_protected_price_change_detects_approval_fields(self) -> None:
        old = SpecialPrice(
            unit_price_usd=25,
            status="Approved",
            note="manual",
            approved_by="accounts@example.com",
            approved_on="2026-01-01",
        )
        same = SpecialPrice(
            unit_price_usd=25,
            status="Approved",
            note="manual",
            approved_by="accounts@example.com",
            approved_on="2026-01-01",
        )
        changed = SpecialPrice(
            unit_price_usd=30,
            status="Approved",
            note="manual",
            approved_by="accounts@example.com",
            approved_on="2026-01-01",
        )

        self.assertFalse(protected_price_changed(old, same))
        self.assertTrue(protected_price_changed(old, changed))
        self.assertTrue(protected_price_changed(None, changed))

    def test_special_shape_decision_separates_permission_and_invalidation(self) -> None:
        old_geometry = PieceGeometry(piece_type="Special", width_cm=50, length_cm=100)
        new_geometry = PieceGeometry(piece_type="Special", width_cm=60, length_cm=100)
        estimated = SpecialPrice(status="Estimated")

        safe = evaluate_special_shape(
            old_geometry=old_geometry,
            current_geometry=new_geometry,
            old_price=estimated,
            current_price=estimated,
            drawing_changed=False,
            drawing_has_elements=True,
            default_edge_changed=False,
            approval_action=False,
        )
        self.assertTrue(safe.pricing_basis_changed)
        self.assertTrue(safe.safe_geometry_invalidation)
        self.assertFalse(safe.requires_price_permission)
        self.assertTrue(safe.reset_price)
        self.assertEqual(safe.documentation_status, "Documented")

        approved = SpecialPrice(
            unit_price_usd=80,
            status="Approved",
            note="approved",
            approved_by="accounts@example.com",
            approved_on="2026-01-01",
        )
        protected = evaluate_special_shape(
            old_geometry=old_geometry,
            current_geometry=old_geometry,
            old_price=estimated,
            current_price=approved,
            drawing_changed=False,
            drawing_has_elements=True,
            default_edge_changed=False,
            approval_action=False,
        )
        self.assertTrue(protected.requires_price_permission)
        self.assertFalse(protected.reset_price)

    def test_price_reset_values_preserve_status_contract(self) -> None:
        special = reset_price_values("Special")
        regular = reset_price_values("Regular")
        self.assertEqual(special["special_shape_price_status"], "Estimated")
        self.assertEqual(regular["special_shape_price_status"], "Not Applicable")
        self.assertIsNone(special["special_shape_price_approved_on"])

    def test_corner_cut_predicate_covers_diagonal_and_l_shaped_types(self) -> None:
        from almdina_erp.almdina_erp.domain.orders.piece_policy import (
            L_SHAPED_CORNER_TYPE,
            PIECE_TYPES,
            corner_cut_arabic_label,
            is_corner_cut,
            pending_custom_edge_price_labels,
        )

        self.assertIn("L-Shaped Corner", PIECE_TYPES)
        self.assertTrue(is_corner_cut("Clipped Corner"))
        self.assertTrue(is_corner_cut(L_SHAPED_CORNER_TYPE))
        self.assertFalse(is_corner_cut("Regular"))
        self.assertFalse(is_corner_cut("Special"))
        self.assertEqual(corner_cut_arabic_label("Clipped Corner"), "درفة زاوية مقصوصة")
        self.assertEqual(corner_cut_arabic_label(L_SHAPED_CORNER_TYPE), "درفة زاوية L")
        self.assertEqual(
            pending_custom_edge_price_labels(
                [
                    {"piece_type": "Clipped Corner", "clipped_corner_edge_price_status": "Unpriced"},
                    {
                        "piece_type": "L-Shaped Corner",
                        "clipped_corner_edge_price_status": "Unpriced",
                    },
                    {"piece_type": "Clipped Corner", "clipped_corner_edge_price_status": "Priced"},
                ]
            ),
            ("درفة زاوية مقصوصة 1", "درفة زاوية L 2"),
        )


if __name__ == "__main__":
    unittest.main()
