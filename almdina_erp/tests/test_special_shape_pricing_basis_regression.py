from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "piece_policy.py"


class TestSpecialShapePricingBasisRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        namespace = runpy.run_path(str(DOMAIN_PATH))
        cls.PieceGeometry = namespace["PieceGeometry"]
        cls.SpecialPrice = namespace["SpecialPrice"]
        cls.evaluate_special_shape = staticmethod(namespace["evaluate_special_shape"])
        cls.pricing_basis_changed = staticmethod(namespace["pricing_basis_changed"])

    def _geometry(self, **overrides):
        values = {
            "piece_type": "Special",
            "width_cm": 90,
            "length_cm": 210,
            "qty": 2,
            "allow_rotation": 0,
            "clipped_corner_position": "",
            "clipped_corner_width_cm": 0,
            "clipped_corner_length_cm": 0,
            "edge_long_right": 0,
            "edge_long_left": 0,
            "edge_width_top": 0,
            "edge_width_bottom": 0,
            "edge_type": "",
        }
        values.update(overrides)
        return self.PieceGeometry(**values)

    def _approved_price(self):
        return self.SpecialPrice(
            unit_price_usd=125,
            status="Approved",
            note="reviewed",
            approved_by="pricing@example.com",
            approved_on="2026-08-20 12:00:00",
        )

    def _decision(
        self,
        old_geometry,
        current_geometry,
        *,
        drawing_changed=False,
        default_edge_changed=False,
    ):
        price = self._approved_price()
        return self.evaluate_special_shape(
            old_geometry=old_geometry,
            current_geometry=current_geometry,
            old_price=price,
            current_price=price,
            drawing_changed=drawing_changed,
            drawing_has_elements=True,
            default_edge_changed=default_edge_changed,
            approval_action=False,
        )

    def test_drawing_change_keeps_reviewed_price_current(self) -> None:
        geometry = self._geometry()

        decision = self._decision(
            geometry,
            geometry,
            drawing_changed=True,
        )

        self.assertTrue(decision.geometry_changed)
        self.assertFalse(decision.pricing_basis_changed)
        self.assertFalse(decision.reset_price)

    def test_piece_edge_changes_keep_reviewed_price_current(self) -> None:
        old_geometry = self._geometry()
        current_geometry = self._geometry(
            edge_long_right=1,
            edge_long_left=1,
            edge_width_top=1,
            edge_width_bottom=1,
            edge_type="ABS",
        )

        decision = self._decision(old_geometry, current_geometry)

        self.assertTrue(decision.geometry_changed)
        self.assertFalse(decision.pricing_basis_changed)
        self.assertFalse(decision.reset_price)

    def test_default_edge_change_keeps_reviewed_price_current(self) -> None:
        geometry = self._geometry()

        decision = self._decision(
            geometry,
            geometry,
            default_edge_changed=True,
        )

        self.assertFalse(decision.pricing_basis_changed)
        self.assertFalse(decision.reset_price)

    def test_other_geometry_details_do_not_define_price_basis(self) -> None:
        old_geometry = self._geometry()
        current_geometry = self._geometry(
            allow_rotation=1,
            clipped_corner_position="Top Right",
            clipped_corner_width_cm=12,
            clipped_corner_length_cm=18,
        )

        decision = self._decision(old_geometry, current_geometry)

        self.assertTrue(decision.geometry_changed)
        self.assertFalse(decision.pricing_basis_changed)
        self.assertFalse(decision.reset_price)

    def test_only_piece_type_dimensions_and_quantity_invalidate_price(self) -> None:
        old_geometry = self._geometry()
        cases = {
            "piece_type": self._geometry(piece_type="Regular"),
            "width_cm": self._geometry(width_cm=91),
            "length_cm": self._geometry(length_cm=211),
            "qty": self._geometry(qty=3),
        }

        for fieldname, current_geometry in cases.items():
            with self.subTest(fieldname=fieldname):
                decision = self._decision(old_geometry, current_geometry)
                self.assertTrue(decision.pricing_basis_changed)
                self.assertTrue(decision.reset_price)

    def test_new_row_does_not_report_a_changed_price_basis(self) -> None:
        self.assertFalse(
            self.pricing_basis_changed(None, self._geometry())
        )


if __name__ == "__main__":
    unittest.main()
