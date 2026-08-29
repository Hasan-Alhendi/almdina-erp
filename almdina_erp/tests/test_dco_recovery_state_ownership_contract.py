from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import (
    canonical_json,
    fingerprint_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "almdina_erp"
PUBLIC = APP_ROOT / "public" / "js"
REFERENCE = REPO_ROOT / "docs" / "reference"
RECOVERY_CONTRACT = REFERENCE / "16_DCO_RECOVERY_STATE_OWNERSHIP.md"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestDcoRecoveryStateOwnershipContract(unittest.TestCase):
    def test_r1_contract_is_indexed_and_covers_every_required_decision(self) -> None:
        index = source(REFERENCE / "README.md")
        contract = source(RECOVERY_CONTRACT)

        self.assertIn("16_DCO_RECOVERY_STATE_OWNERSHIP.md", index)
        for required in (
            "Recovery State Ownership Map",
            "Recovery Payload / Projection",
            "NEW lifecycle contract",
            "EDIT lifecycle contract",
            "session_origin_modified",
            "expected_server_modified",
            "Existing internal pre-plan checkpoint save",
            "First-insert idempotency and reconciliation",
            "Scanner, drawing, and asset durability",
            "InvoiceInputProjection v1",
            "CuttingPlanInputProjection",
            "Multi-tab ownership and conflict rules",
        ):
            self.assertIn(required, contract)

        for forbidden_scope in (
            "does **not** implement IndexedDB",
            "does not implement persistence",
            "does not autosave",
            "No timer delay is evidence",
        ):
            self.assertIn(forbidden_scope, contract)

    def test_existing_document_and_edit_session_owners_are_characterized(self) -> None:
        document_context = source(
            PUBLIC
            / "door_cutting_order"
            / "core"
            / "door_cutting_order_document_context.js"
        )
        revision = source(
            PUBLIC
            / "door_cutting_order"
            / "core"
            / "door_cutting_order_revision_ux.js"
        )

        self.assertIn(
            "function promotePendingInsert(frm, currentIdentity = formIdentity(frm))",
            document_context,
        )
        self.assertIn("frappe.model.new_names", document_context)
        self.assertIn("aliases.add(pending.token.identity)", document_context)
        self.assertIn("aliases.add(promotedIdentity)", document_context)

        checkpoint = revision.split(
            "async function persistOrderEditCheckpoint", 1
        )[1].split("function confirmEditSession", 1)[0]
        self.assertIn("frm.is_new()", checkpoint)
        self.assertIn("markEditSessionSticky(frm);", checkpoint)
        self.assertIn("frm.__almdina_preserve_edit_session_after_save = true;", checkpoint)
        self.assertIn("await frm.save();", checkpoint)

    def test_checkpoint_remains_order_input_persistence_not_plan_autosave(self) -> None:
        fast_save = source(
            PUBLIC
            / "door_cutting_order"
            / "cutting_plan"
            / "door_cutting_order_fast_save_ux.js"
        )
        persist = fast_save.split(
            "async function persistPendingOrderInputs", 1
        )[1].split("function renderStaleState", 1)[0]

        self.assertIn("__almdina_pending_order_input_persistence", persist)
        self.assertIn("persistOrderEditCheckpoint", persist)
        self.assertNotIn("bootstrapPlan", persist)
        self.assertNotIn("commitPreview", persist)
        self.assertNotIn("setTimeout", persist)

    def test_workspace_state_and_reconciliation_keep_their_existing_owners(self) -> None:
        store = source(
            PUBLIC
            / "door_cutting_order"
            / "core"
            / "door_cutting_order_workspace_store.js"
        )
        coordinator = source(
            PUBLIC
            / "door_cutting_order"
            / "core"
            / "door_cutting_order_workspace_sync_coordinator.js"
        )
        plan_state = source(
            PUBLIC
            / "door_cutting_order"
            / "cutting_plan"
            / "door_cutting_order_plan_workspace_state.js"
        )
        cost_state = source(
            PUBLIC
            / "door_cutting_order"
            / "costing"
            / "door_cutting_order_cost_workspace_state.js"
        )
        plan_edit = source(
            PUBLIC
            / "door_cutting_order"
            / "cutting_plan"
            / "door_cutting_order_plan_edit_session_ux.js"
        )
        contract = source(RECOVERY_CONTRACT)

        self.assertIn("window.AlmdinaWorkspaceStore", store)
        self.assertIn("window.AlmdinaWorkspaceSyncCoordinator", coordinator)
        self.assertIn("__almdina_pending_server_modified", coordinator)
        self.assertIn("AlmdinaWorkspaceStore", plan_state)
        self.assertIn("AlmdinaWorkspaceStore", cost_state)
        for field in (
            "packing_mode",
            "cutting_machine_type",
            "kerf_mm",
            "trim_margin_mm",
            "optimization_time_limit_sec",
        ):
            self.assertIn(f'"{field}"', plan_edit)
            self.assertIn(field, contract)

    def test_cutting_plan_fingerprint_is_deterministic_versioned_input(self) -> None:
        workspace = source(
            APP_ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "cutting_plan_workspace.py"
        )
        version = source(
            APP_ROOT
            / "almdina_erp"
            / "application"
            / "cutting"
            / "version.py"
        )

        fingerprint_body = workspace.split(
            "def plan_input_fingerprint", 1
        )[1].split("def calculate_system_plan", 1)[0]
        for field in (
            '"version": 1',
            '"order_revision"',
            '"board"',
            '"settings"',
            '"pieces"',
        ):
            self.assertIn(field, fingerprint_body)
        self.assertNotIn("ENGINE_VERSION", fingerprint_body)
        self.assertIn('ENGINE_VERSION = "2.1.0-fast-save"', version)

        left = {"settings": {"kerf_mm": 3}, "version": 1, "pieces": []}
        right = {"pieces": [], "version": 1, "settings": {"kerf_mm": 3}}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))
        self.assertEqual(len(fingerprint_payload(left)), 64)

    def test_invoice_stays_a_server_generated_read_model(self) -> None:
        service = source(
            APP_ROOT / "almdina_erp" / "services" / "cost_document_service.py"
        )
        frontend = source(
            PUBLIC
            / "door_cutting_order"
            / "costing"
            / "door_cutting_order_financial_documents_ux.js"
        )
        contract = source(RECOVERY_CONTRACT)

        self.assertIn("build_customer_invoice_document(order_snapshot, pieces)", service)
        self.assertIn("get_customer_invoice_document", frontend)
        self.assertIn("regenerate the read model before print", contract)
        self.assertIn("never creates a Sales Invoice aggregate", contract)

    def test_scanner_and_drawing_assets_keep_their_current_durable_owners(self) -> None:
        scanner = source(
            PUBLIC
            / "special_shape_documentation"
            / "infrastructure"
            / "scanner_bridge.js"
        )
        document = source(
            PUBLIC
            / "special_shape_documentation"
            / "domain"
            / "document.js"
        )
        service = source(
            APP_ROOT
            / "almdina_erp"
            / "services"
            / "special_shape_workspace_service.py"
        )

        self.assertNotIn("frappe.call", scanner)
        self.assertNotIn("special_shape_drawing_json", scanner)
        self.assertIn('startsWith("/private/files/")', document)
        self.assertIn("is_private=1", service)
        self.assertIn('"special_shape_drawing_json": documentation_text', service)
        self.assertIn(
            'frappe.db.set_value("Door Cutting Order Detail"',
            service,
        )

    def test_dco_recovery_projection_contains_only_editable_requirements(self) -> None:
        contract = source(RECOVERY_CONTRACT)
        schema = json.loads(
            source(
                APP_ROOT
                / "almdina_erp"
                / "doctype"
                / "door_cutting_order_detail"
                / "door_cutting_order_detail.json"
            )
        )
        fields = {field["fieldname"]: field for field in schema["fields"]}

        for editable_input in (
            "piece_type",
            "width_cm",
            "length_cm",
            "qty",
            "allow_rotation",
            "special_shape_drawing_json",
            "special_shape_geometry_json",
        ):
            self.assertIn(editable_input, contract)
            self.assertFalse(fields[editable_input].get("read_only", 0))

        for derived in (
            "cut_width_cm",
            "area_m2",
            "edge_meters",
            "edge_cost_usd",
            "special_shape_status",
        ):
            self.assertTrue(fields[derived].get("read_only", 0))
        self.assertIn("cut sizes, areas, edge meters/types/thicknesses, totals, prices", contract)


if __name__ == "__main__":
    unittest.main()
