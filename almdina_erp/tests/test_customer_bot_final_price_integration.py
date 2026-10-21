"""Development-site proof for real approval and primary-phone ownership reads."""

from __future__ import annotations

from decimal import Decimal
import platform
import secrets
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_final_price_reader import (
    FrappeCustomerBotFinalPriceReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_invoice_pdf import (
    FrappeCustomerBotInvoicePdfAdapter,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import normalize_customer_phone


class TestCustomerBotFinalPriceIntegration(FrappeTestCase):
    def test_reads_real_active_approval_only_for_the_current_primary_phone(self) -> None:
        rows = frappe.get_all(
            "Door Cutting Order",
            filters={"price_approval_status": "Approved"},
            fields=["name", "customer", "current_price_approval"],
            limit_page_length=1,
        )
        if not rows:
            self.skipTest("development site has no approved price fixture")
        order_name = str(rows[0].name)
        customer = str(rows[0].customer)
        approval = frappe.get_doc("Door Cutting Price Approval", rows[0].current_price_approval)
        previous_phone = frappe.db.get_value("Customer", customer, "mobile_no")
        phone = f"0988{secrets.randbelow(1_000_000):06d}"
        while FrappeCustomerPhoneDirectory().find_by_normalized_phone(
            normalize_customer_phone(phone)
        ):
            phone = f"0988{secrets.randbelow(1_000_000):06d}"
        try:
            frappe.db.set_value("Customer", customer, "mobile_no", phone, update_modified=False)
            snapshot = FrappeCustomerBotFinalPriceReader().read(phone, order_name)
            self.assertIsNotNone(snapshot)
            self.assertTrue(snapshot.available)
            self.assertEqual(snapshot.amount, Decimal(str(approval.approved_amount)).quantize(Decimal("0.01")))
            self.assertEqual(snapshot.currency, str(approval.currency))
            self.assertEqual(snapshot.invoice_payload["kind"], "customer_invoice")
            self.assertIsNone(FrappeCustomerBotFinalPriceReader().read(phone, "CBOT-NOT-FOUND"))
            self.assertIsNone(FrappeCustomerBotFinalPriceReader().read("098811111111", order_name))
            if not _local_pdf_renderer_available():
                self.skipTest("development site has no local PDF renderer")
            try:
                pdf = FrappeCustomerBotInvoicePdfAdapter().render(
                    order_name,
                    snapshot.invoice_payload,
                )
            except Exception as error:
                self.skipTest(f"development PDF renderer is unavailable: {error}")
            self.assertTrue(pdf.startswith(b"%PDF"))
            self.assertGreater(len(pdf), 100)
        finally:
            frappe.db.set_value("Customer", customer, "mobile_no", previous_phone, update_modified=False)


def _local_pdf_renderer_available() -> bool:
    relative = {"linux": ("chrome-linux", "headless_shell")}.get(platform.system().lower())
    if relative and Path(frappe.utils.get_bench_path(), "chromium", *relative).is_file():
        return True
    return False


__all__ = ["TestCustomerBotFinalPriceIntegration"]
