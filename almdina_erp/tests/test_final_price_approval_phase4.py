"""Phase 4: Cost-tab final-price approval UI wiring contracts."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
COSTING = PUBLIC / "costing"
CORE = PUBLIC / "core"
TRANSLATIONS = ROOT / "translations" / "ar.csv"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestFinalPriceApprovalPhase4(unittest.TestCase):
    def test_cost_lazy_bundle_registers_approval_ux_after_edit_session(self) -> None:
        registry = _read(CORE / "door_cutting_order_workspace_asset_registry.js")
        edit_idx = registry.index("door_cutting_order_cost_edit_session_ux.js")
        approval_idx = registry.index("door_cutting_order_final_price_approval_ux.js")
        self.assertGreater(approval_idx, edit_idx)
        self.assertIn("AlmdinaFinalPriceApprovalUX", registry)

    def test_cost_workspace_api_exposes_approve_final_price(self) -> None:
        api = _read(COSTING / "door_cutting_order_cost_workspace_api.js")
        self.assertIn(
            "almdina_erp.almdina_erp.services.final_price_approval_service.approve_order_final_price",
            api,
        )
        self.assertIn("approveFinalPrice", api)
        self.assertIn("expected_price_basis_token", api)

    def test_presenter_keeps_total_card_and_approval_slot(self) -> None:
        presenter = _read(COSTING / "door_cutting_order_cost_presenter.js")
        self.assertIn("dco-invoice-total-card", presenter)
        self.assertIn("dco-invoice-total-label", presenter)
        self.assertIn("dco-invoice-total-end", presenter)
        self.assertIn("dco-invoice-total-amount", presenter)
        self.assertIn("data-price-approval-panel", presenter)
        self.assertIn("dco-price-approval-slot", presenter)
        # End group order: approval panel, then amount as last child.
        end_block = presenter.split("dco-invoice-total-end", 1)[1]
        self.assertLess(
            end_block.index("approvalSlot"),
            end_block.index("${amount}"),
        )

    def test_adapter_reconciles_final_price_approval_after_total_card(self) -> None:
        adapter = _read(COSTING / "door_cutting_order_cost_workspace_presenter_adapter.js")
        total_idx = adapter.index("reconcileInvoiceTotalCard(frm)")
        approval_idx = adapter.index("reconcileFinalPriceApproval(frm)")
        self.assertGreater(approval_idx, total_idx)
        self.assertIn("AlmdinaFinalPriceApprovalUX", adapter)

    def test_edit_session_consumes_server_can_edit_cost_settings(self) -> None:
        edit = _read(COSTING / "door_cutting_order_cost_edit_session_ux.js")
        self.assertIn("can_edit_cost_settings", edit)
        self.assertIn("Cost settings are locked because the final price is approved.", edit)
        self.assertIn(
            "price approval must never imply edit_cost_settings",
            edit,
        )

    def test_approval_ux_consumes_server_decisions_without_fingerprint_ui(self) -> None:
        ux = _read(COSTING / "door_cutting_order_final_price_approval_ux.js")
        for needle in (
            "can_approve_final_price",
            "final_price_approval_blocker",
            "price_basis_token",
            "approve_final_price",
            "Price approval status",
            "Approve final price",
            "AlmdinaDcoEditSessionCoordinator",
            "alm-btn-primary",
        ):
            self.assertIn(needle, ux)
        self.assertNotIn("frm.reload_doc", ux)
        # Panel markup must not interpolate the token or fingerprint into HTML.
        self.assertNotIn("${esc(token)", ux)
        self.assertNotIn("fingerprint_formula_version}", ux)
        self.assertIn("var(--alm-primary", ux)

    def test_arabic_translation_keys_for_cost_tab_ui(self) -> None:
        ar = _read(TRANSLATIONS)
        for key in (
            "Price approval status",
            "Approve final price",
            "Approved",
            "Unapproved",
            "Cost settings are locked because the final price is approved.",
            "Save or cancel unsaved changes before approving the final price.",
            "The price basis changed. Review the total, then approve again.",
        ):
            self.assertTrue(
                f"{key}," in ar or f'"{key}",' in ar,
                msg=f"missing Arabic translation for: {key}",
            )


if __name__ == "__main__":
    unittest.main()
