from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.orders.plan_payloads import (
    PlanBoardInput,
    PlanCutInput,
    PlanMetadataPiece,
    PlanOptimizerSettings,
    PlanPieceInput,
    build_plan_input_payload,
    build_plan_metadata_payload,
)
from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import (
    canonical_json,
    fingerprint_payload,
)


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "plan_fingerprint.py"
APPLICATION_PATH = ROOT / "almdina_erp" / "application" / "orders" / "plan_payloads.py"
PLAN_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "plan_adapter.py"
)


class TestPlanFingerprintDomain(unittest.TestCase):
    def test_canonical_json_and_hash_are_order_independent(self) -> None:
        first = {"b": 2, "a": {"z": 1, "x": "أ"}}
        second = {"a": {"x": "أ", "z": 1}, "b": 2}
        expected_json = '{"a":{"x":"\\u0623","z":1},"b":2}'
        expected_hash = "ce22c50e62ba1bbb70a3a09dfe38aec1c47b7d6c33c251076334d690f5e9c61d"

        self.assertEqual(canonical_json(first), expected_json)
        self.assertEqual(canonical_json(second), expected_json)
        self.assertEqual(fingerprint_payload(first), expected_hash)
        self.assertEqual(fingerprint_payload(second), expected_hash)


class TestPlanPayloadApplication(unittest.TestCase):
    def test_input_payload_preserves_existing_contract(self) -> None:
        payload = build_plan_input_payload(
            version=1,
            board=PlanBoardInput(item="MDF 18mm White", width_mm=1220.0, length_mm=2440.0),
            cut=PlanCutInput(
                kerf_mm=4.0,
                trim_margin_mm=10.0,
                packing_mode="Auto Pro",
                machine_type="Panel Saw",
                time_limit_sec=10.0,
            ),
            optimizer=PlanOptimizerSettings(
                exact_piece_limit=40,
                min_remnant_width_mm=150.0,
                min_remnant_length_mm=300.0,
                min_remnant_area_m2=0.08,
            ),
            pieces=[
                PlanPieceInput(
                    index=1,
                    width_cm=60.0,
                    length_cm=80.0,
                    qty=2,
                    allow_rotation=1,
                    piece_type="Clipped Corner",
                    clipped_corner_position="Top Right",
                    clipped_corner_width_cm=12.0,
                    clipped_corner_length_cm=16.0,
                )
            ],
        )

        self.assertEqual(
            payload,
            {
                "version": 1,
                "board": {
                    "item": "MDF 18mm White",
                    "width_mm": 1220.0,
                    "length_mm": 2440.0,
                },
                "cut": {
                    "kerf_mm": 4.0,
                    "trim_margin_mm": 10.0,
                    "packing_mode": "Auto Pro",
                    "machine_type": "Panel Saw",
                    "time_limit_sec": 10.0,
                },
                "optimizer_settings": {
                    "exact_piece_limit": 40,
                    "min_remnant_width_mm": 150.0,
                    "min_remnant_length_mm": 300.0,
                    "min_remnant_area_m2": 0.08,
                },
                "pieces": [
                    {
                        "index": 1,
                        "width_cm": 60.0,
                        "length_cm": 80.0,
                        "qty": 2,
                        "allow_rotation": 1,
                        "piece_type": "Clipped Corner",
                        "clipped_corner_position": "Top Right",
                        "clipped_corner_width_cm": 12.0,
                        "clipped_corner_length_cm": 16.0,
                    }
                ],
            },
        )

    def test_metadata_payload_preserves_four_effective_side_profiles(self) -> None:
        drawing = '{"version":1,"elements":[]}'
        payload = build_plan_metadata_payload(
            default_edge_type="2cm Normal",
            edge_color="White",
            pieces=[
                PlanMetadataPiece(
                    index=1,
                    piece_type="Special",
                    edge_long_right=1,
                    edge_long_left=1,
                    edge_width_top=1,
                    edge_width_bottom=0,
                    edge_type="",
                    edge_rate_usd=0.5,
                    edge_cost_usd=1.4,
                    area_m2=0.48,
                    notes="Flower shape",
                    drawing_token=drawing,
                    special_shape_status="Documented",
                    edge_long_right_type="2cm Glossy",
                    edge_long_left_type="2cm Normal",
                    edge_width_top_type="2cm Gold",
                )
            ],
        )

        self.assertEqual(payload["default_edge_type"], "2cm Normal")
        self.assertEqual(payload["edge_color"], "White")
        piece = payload["pieces"][0]
        self.assertEqual(piece["edge_long_right_type"], "2cm Glossy")
        self.assertEqual(piece["edge_long_left_type"], "2cm Normal")
        self.assertEqual(piece["edge_width_top_type"], "2cm Gold")
        self.assertEqual(piece["edge_width_bottom_type"], "")
        self.assertEqual(
            piece["drawing_hash"],
            hashlib.sha256(drawing.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(piece["special_shape_status"], "Documented")

    def test_fingerprint_matches_the_previous_canonical_algorithm(self) -> None:
        payload = {"version": 1, "pieces": [{"index": 1, "qty": 2}]}
        legacy = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(fingerprint_payload(payload), legacy)


class TestPlanPayloadArchitecture(unittest.TestCase):
    def test_domain_and_application_are_framework_independent(self) -> None:
        for path in (DOMAIN_PATH, APPLICATION_PATH):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotIn("import frappe", source)
                self.assertNotIn("from frappe", source)
                self.assertNotIn("import erpnext", source)
                self.assertNotIn(".services", source)

    def test_active_plan_adapter_delegates_payloads_and_hashes(self) -> None:
        source = PLAN_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("application.orders.plan_payloads", source)
        self.assertIn("domain.orders.plan_fingerprint", source)
        self.assertIn("build_plan_input_payload", source)
        self.assertIn("build_plan_metadata_payload", source)
        self.assertIn("fingerprint_payload", source)
        self.assertNotIn("import hashlib", source)
        self.assertNotIn("hashlib.sha256", source)

    def test_free_text_board_description_is_owned_by_active_plan_adapter(self) -> None:
        source = PLAN_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("description = str(", source)
        self.assertIn("item=description", source)
        self.assertIn('payload["board"]["description"] = description', source)


if __name__ == "__main__":
    unittest.main()
