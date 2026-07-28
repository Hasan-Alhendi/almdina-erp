from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    PieceGeometry,
    PiecePolicyError,
    SpecialPrice,
    drawing_token,
    evaluate_special_shape,
    geometry_changed,
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


if __name__ == "__main__":
    unittest.main()
