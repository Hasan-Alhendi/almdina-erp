"""Phase 5: Door Cutting Order list filter and price-approval badge contracts."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST_JS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)
LIST_CSS = ROOT / "public" / "css" / "door_cutting_order_list.css"
MOBILE_CSS = ROOT / "public" / "css" / "door_cutting_order_mobile_list.css"
DOCTYPE_JSON = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)
TRANSLATIONS = ROOT / "translations" / "ar.csv"
APPROVAL_SERVICE = ROOT / "almdina_erp" / "services" / "final_price_approval_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestFinalPriceApprovalPhase5(unittest.TestCase):
    def test_list_filter_uses_fixed_price_approval_status_values(self) -> None:
        source = _read(LIST_JS)
        self.assertIn('PRICE_APPROVAL_FILTER_FIELDNAME = "price_approval_status"', source)
        self.assertIn("priceApprovalFilterConfig({ localize: false })", source)
        self.assertIn('PRICE_APPROVAL_FILTER_ALL_LABEL = "All price statuses"', source)
        self.assertIn('value: PRICE_APPROVAL_STATUS_APPROVED', source)
        self.assertIn('value: PRICE_APPROVAL_STATUS_UNAPPROVED', source)
        self.assertIn('"price_approval_status"', source)
        # Server-side Select filter via Frappe standard contract; no custom query expand.
        self.assertIn("condition: \"=\"", source)
        self.assertNotIn("customer_quote_status", source.split("priceApprovalFilterConfig")[1][:800])

    def test_list_loads_status_field_without_approval_record_or_financial_payload(self) -> None:
        source = _read(LIST_JS)
        self.assertIn('"price_approval_status"', source)
        self.assertNotIn("current_price_approval", source)
        self.assertNotIn("approved_amount", source)
        self.assertNotIn("pricing_basis_fingerprint", source)
        self.assertNotIn("price_basis_token", source)
        self.assertNotIn("get_list(\"Door Cutting Price Approval\"", source)
        self.assertNotIn("Door Cutting Price Approval", source)

    def test_list_badge_is_independent_of_operational_status(self) -> None:
        source = _read(LIST_JS)
        self.assertIn("applyDesktopPriceApprovalBadges", source)
        self.assertIn("renderPriceApprovalBadge", source)
        self.assertIn("dco-list-price-approval", source)
        self.assertIn("priceApprovalStatus", source)
        # Operational pill remains separate from price badge.
        self.assertIn("renderStatusPill(model.state)", source)
        self.assertIn("renderPriceApprovalBadge(model)", source)

    def test_filter_slot_and_badge_styles_are_list_scoped(self) -> None:
        css = _read(LIST_CSS)
        mobile = _read(MOBILE_CSS)
        self.assertIn(
            '.dco-order-list .dco-status-filter-slot [data-fieldname="price_approval_status"]',
            css,
        )
        self.assertIn(".dco-order-list .dco-list-price-approval.is-approved", css)
        self.assertIn(".dco-order-list .dco-list-price-approval.is-unapproved", css)
        self.assertIn(
            ".dco-order-list.dco-order-card-layout .dco-list-price-approval.is-approved",
            mobile,
        )

    def test_doctype_keeps_status_enum_without_list_column_default(self) -> None:
        doctype = _read(DOCTYPE_JSON)
        self.assertIn('"fieldname":"price_approval_status"', doctype)
        self.assertIn('"options":"Unapproved\\nApproved"', doctype)
        # Badge/filter consume add_fields; column stays off by default.
        self.assertIn('"in_list_view":0', doctype)

    def test_arabic_keys_for_list_filter(self) -> None:
        ar = _read(TRANSLATIONS)
        self.assertIn("All price statuses,كل حالات السعر", ar)
        self.assertIn("Price approval status,حالة السعر", ar)
        self.assertIn("Approved,معتمد", ar)
        self.assertIn("Unapproved,غير معتمد", ar)

    def test_service_alias_regression_remains_in_place(self) -> None:
        service = _read(APPROVAL_SERVICE)
        self.assertIn(
            "approve_order_final_price as run_approve_order_final_price",
            service,
        )
        self.assertIn("run_approve_order_final_price(", service)


if __name__ == "__main__":
    unittest.main()
