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
from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    is_financial_plan_key,
    sanitize_plan_snapshot,
    sanitize_plan_snapshot_json,
)
from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import (
    canonical_json,
    fingerprint_payload,
)


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "plan_fingerprint.py"
APPLICATION_PATH = ROOT / "almdina_erp" / "application" / "orders" / "plan_payloads.py"
SNAPSHOT_SECURITY_PATH = (
    ROOT / "almdina_erp" / "application" / "orders" / "plan_snapshot_security.py"
)
PLAN_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "plan_adapter.py"
)
SAVE_GATEWAY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "save_gateway.py"
)
CUTTING_PLAN_WORKSPACE_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "cutting_plan_workspace.py"
)
ORDER_SAVE_PATH = ROOT / "almdina_erp" / "application" / "orders" / "process_order_save.py"
SNAPSHOT_SERVICE_PATH = ROOT / "almdina_erp" / "services" / "cutting_plan_snapshot_service.py"
API_PATH = ROOT / "almdina_erp" / "api.py"
COST_SERVICE_PATH = ROOT / "almdina_erp" / "services" / "cost_service.py"
PATCHES_PATH = ROOT / "patches.txt"


def _nested_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_nested_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_nested_keys(item))
    return keys


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
        self.assertNotIn("drawing_hash", piece)
        self.assertNotIn("special_shape_status", piece)

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

    def test_plan_snapshot_sanitizer_removes_nested_financial_data(self) -> None:
        source = {
            "engine_version": "v3",
            "validation": {"is_valid": True},
            "approved_cost": {
                "board_rate_usd": 24.0,
                "total_cost_usd": 52.0,
            },
            "customer_quote_status": "Approved",
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {
                            "id": "1-1",
                            "x": 5,
                            "y": 7,
                            "edge_rate_usd": 0.5,
                            "edge_cost_usd": 1.4,
                            "special_shape_final_unit_price_usd": 12.0,
                            "special_shape_price_note": "private price note",
                        }
                    ],
                }
            ],
        }

        sanitized = sanitize_plan_snapshot(source)
        keys = _nested_keys(sanitized)

        self.assertEqual(sanitized["engine_version"], "v3")
        self.assertTrue(sanitized["validation"]["is_valid"])
        self.assertEqual(sanitized["sheets"][0]["pieces"][0]["x"], 5)
        self.assertNotIn("approved_cost", keys)
        self.assertNotIn("customer_quote_status", keys)
        self.assertFalse([key for key in keys if is_financial_plan_key(key)])
        self.assertIn("approved_cost", source)
        self.assertIn("edge_cost_usd", source["sheets"][0]["pieces"][0])

    def test_plan_snapshot_json_preserves_safe_payload_and_cleans_legacy_payload(self) -> None:
        safe = '{"validation":{"is_valid":true},"sheets":[]}'
        self.assertEqual(sanitize_plan_snapshot_json(safe), safe)

        legacy = json.dumps(
            {
                "validation": {"is_valid": True},
                "total_cost_usd": 99,
                "sheets": [{"pieces": [{"edge_rate_usd": 0.5, "x": 1}]}],
            },
            ensure_ascii=False,
        )
        cleaned = json.loads(sanitize_plan_snapshot_json(legacy))
        self.assertEqual(cleaned["sheets"][0]["pieces"][0], {"x": 1})
        self.assertNotIn("total_cost_usd", cleaned)

    def test_malformed_snapshot_fails_closed(self) -> None:
        raw = '{"approved_cost":{"total_cost_usd":99},invalid}'
        self.assertEqual(sanitize_plan_snapshot_json(raw), "{}")


class TestPlanPayloadArchitecture(unittest.TestCase):
    def test_domain_and_application_are_framework_independent(self) -> None:
        for path in (DOMAIN_PATH, APPLICATION_PATH, SNAPSHOT_SECURITY_PATH):
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

    def test_non_financial_snapshot_contract_is_wired_across_persistence_and_api(self) -> None:
        order_save = ORDER_SAVE_PATH.read_text(encoding="utf-8")
        save_gateway = SAVE_GATEWAY_PATH.read_text(encoding="utf-8")
        workspace = CUTTING_PLAN_WORKSPACE_PATH.read_text(encoding="utf-8")
        snapshot_service = SNAPSHOT_SERVICE_PATH.read_text(encoding="utf-8")
        cost_service = COST_SERVICE_PATH.read_text(encoding="utf-8")
        api = API_PATH.read_text(encoding="utf-8")
        patches = PATCHES_PATH.read_text(encoding="utf-8")

        # A4: ordinary DCO persistence no longer owns Cutting Plan snapshots.
        self.assertNotIn("sanitize_plan_snapshots", order_save)
        self.assertNotIn("sanitize_plan_snapshot_json", order_save)
        self.assertNotIn("sanitize_plan_snapshot_json", save_gateway)
        self.assertNotIn('"cutting_plan_json"', save_gateway)
        self.assertNotIn('"system_plan_json"', save_gateway)
        self.assertNotIn('"custom_plan_json"', save_gateway)

        # Canonical Cutting Plan calculation/import owns sanitizing geometry.
        self.assertIn("sanitize_plan_snapshot", workspace)
        self.assertIn("snapshot = sanitize_plan_snapshot(outcome.snapshot)", workspace)
        self.assertIn("snapshot = sanitize_plan_snapshot(raw_snapshot)", workspace)
        self.assertIn("plan.snapshot_json = frappe.as_json(snapshot)", workspace)

        # A6.3: the pre-cutover DCO snapshot persistence surface is retired and
        # must never regain geometry sanitization, plan costs, or persistence.
        self.assertIn("_retired_snapshot_api", snapshot_service)
        self.assertNotIn("sanitize_plan_snapshot", snapshot_service)
        self.assertNotIn("plan.board_rate_usd", snapshot_service)
        self.assertNotIn("plan.total_cost_usd", snapshot_service)
        self.assertNotIn("frappe.new_doc", snapshot_service)
        self.assertNotIn("frappe.db.set_value", snapshot_service)
        self.assertNotIn("ignore_permissions", snapshot_service)

        self.assertIn("_sanitize_cutting_plan_snapshot(doc)", cost_service)
        self.assertIn("sanitize_plan_snapshot_json", cost_service)
        self.assertIn("update_modified=False", cost_service)

        self.assertIn("Capability.VIEW_COSTS", api)
        self.assertIn("include_financial", api)
        self.assertIn("document_has_capability", api)
        self.assertIn("doctype_has_capability", api)
        self.assertIn("sanitize_plan_snapshot_json", api)
        self.assertNotIn('"approved_cost":', api)

        self.assertIn(
            "almdina_erp.patches.v1_0.sanitize_historical_plan_snapshots",
            patches,
        )


if __name__ == "__main__":
    unittest.main()
