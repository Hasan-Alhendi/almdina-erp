from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_PATH = ROOT / "almdina_erp" / "domain" / "orders" / "piece_policy.py"
ACTIVE_ADAPTER_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "piece_policy_adapter.py"
)
CONTROLLER_DIR = ROOT / "almdina_erp" / "doctype" / "door_cutting_order"
CONTROLLER_PATH = CONTROLLER_DIR / "door_cutting_order_controller.py"
RETIRED_CONTROLLER_PATHS = (
    CONTROLLER_DIR / "door_cutting_order_fast.py",
    CONTROLLER_DIR / "door_cutting_order_text_board.py",
    CONTROLLER_DIR / "door_cutting_order_domain.py",
    CONTROLLER_DIR / "door_cutting_order_costing.py",
    CONTROLLER_DIR / "door_cutting_order_plan.py",
)
HOOKS_PATH = ROOT / "hooks.py"
COST_PERMISSION_SERVICE_PATH = ROOT / "almdina_erp" / "services" / "cost_permission_service.py"
COST_PERMISSION_UX_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_permissions_ux.js"
)
COST_EDIT_SESSION_UX_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_edit_session_ux.js"
)
COST_PRESENTER_ADAPTER_PATH = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "costing"
    / "door_cutting_order_cost_workspace_presenter_adapter.js"
)


class TestOrderPiecePolicyAdapter(unittest.TestCase):
    def test_piece_policy_domain_has_no_framework_dependencies(self) -> None:
        source = DOMAIN_PATH.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("import erpnext", source)
        self.assertNotIn(".services", source)
        self.assertNotIn(".doctype", source)
        self.assertIn("class SpecialShapeDecision", source)

    def test_active_frappe_adapter_delegates_piece_decisions(self) -> None:
        source = ACTIVE_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("class FrappeOrderPiecePolicyAdapter", source)
        self.assertIn("evaluate_special_shape", source)
        self.assertIn("resolve_clipped_corner", source)
        self.assertIn("def validate_rows", source)
        self.assertIn("def _validate_clipped_corner", source)
        self.assertNotIn("math.isclose", source)

    def test_active_special_price_policy_uses_configurable_capabilities(self) -> None:
        source = ACTIVE_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("document_has_capability", source)
        self.assertIn("Capability.APPROVE_SPECIAL_PRICE", source)
        self.assertIn("Capability.EDIT_SPECIAL_PRICE", source)
        self.assertNotIn("has_special_price_approval_role", source)
        self.assertNotIn("Accounts Management", source)
        self.assertNotIn("System Manager", source)

    def test_canonical_special_price_command_keeps_drawing_optional(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(
            hooks["override_whitelisted_methods"][
                "almdina_erp.almdina_erp.services.special_shape_service."
                "approve_special_piece_price"
            ],
            "almdina_erp.almdina_erp.services.cost_permission_service."
            "approve_special_piece_price",
        )

        source = COST_PERMISSION_SERVICE_PATH.read_text(encoding="utf-8")
        approval_source = source.split("def approve_special_piece_price(", 1)[1].split(
            "@frappe.whitelist()", 1
        )[0]
        self.assertIn("Capability.APPROVE_SPECIAL_PRICE", approval_source)
        self.assertIn("Capability.EDIT_SPECIAL_PRICE", approval_source)
        self.assertIn('piece.piece_type or "Regular"', approval_source)
        self.assertNotIn("special_shape_status", approval_source)
        self.assertNotIn("Documented", approval_source)

    def test_cost_tab_edit_session_owns_inline_special_price_intent(self) -> None:
        permission_source = COST_PERMISSION_UX_PATH.read_text(encoding="utf-8")
        self.assertIn("AlmdinaCostEditSessionUX", permission_source)
        self.assertIn("costEditUx.isEditing(frm)", permission_source)
        self.assertIn(
            "cost_permission_service.approve_special_piece_price",
            permission_source,
        )
        self.assertIn("discardPendingPriceEdits", permission_source)
        self.assertIn("__almdina_pending_price_capability", permission_source)
        self.assertNotIn("frappe.almdina.orderCanEdit(frm)", permission_source)
        self.assertIn('return String(frm.doc.status || "Draft") === "Draft";', permission_source)

        edit_source = COST_EDIT_SESSION_UX_PATH.read_text(encoding="utf-8")
        self.assertIn("flushPendingPriceEdits", edit_source)
        self.assertIn("discardPendingPriceEdits", edit_source)
        self.assertIn("hadPendingPrices", edit_source)
        self.assertIn("{ refresh: false }", edit_source)

        presenter_source = COST_PRESENTER_ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn("__almdina_pending_price_edit", presenter_source)
        self.assertIn("if (piece && piece.__almdina_pending_price_edit) return;", presenter_source)

    def test_active_controller_is_framework_compatible_and_thin(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        self.assertEqual(
            hooks["override_doctype_class"]["Door Cutting Order"],
            "almdina_erp.almdina_erp.doctype.door_cutting_order."
            "door_cutting_order_controller.DoorCuttingOrderController",
        )
        source = CONTROLLER_PATH.read_text(encoding="utf-8")
        self.assertIn("class DoorCuttingOrderController(DoorCuttingOrder)", source)
        self.assertIn("from .door_cutting_order import DoorCuttingOrder", source)
        self.assertIn("FrappeDoorCuttingOrderSaveGateway", source)
        self.assertNotIn("frappe.model.document import Document", source)

    def test_retired_alternate_controller_chain_is_absent(self) -> None:
        for path in RETIRED_CONTROLLER_PATHS:
            with self.subTest(path=path.name):
                self.assertFalse(path.exists(), path)


if __name__ == "__main__":
    unittest.main()
