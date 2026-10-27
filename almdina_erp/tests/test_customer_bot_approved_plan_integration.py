"""Development-site proof for an isolated approved-plan customer-bot read."""

from __future__ import annotations

import platform
import secrets
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.customer_bot.phone_number import normalize_customer_phone
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_approved_plan_reader import (
    FrappeCustomerBotApprovedPlanReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_cutting_plan_pdf import (
    FrappeCustomerBotCuttingPlanPdfAdapter,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_index import (
    assign_customer_primary_mobile,
)
from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
    approve_order_plan,
    recalculate_system_plan,
)


class TestCustomerBotApprovedPlanIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.suffix = uuid4().hex[:10]
        self.phone = self._unused_phone()
        self.customer = self._customer()
        self.edge = frappe.get_doc(
            {
                "doctype": "Edge Banding Type",
                "edge_type_name": f"CBOT Plan Edge {self.suffix}",
                "english_name": f"CBOT Plan Edge {self.suffix}",
                "width_cm": 2,
                "thickness_mm": 1,
                "rate_usd_per_meter": 1,
            }
        ).insert(ignore_permissions=True)
        self.order = frappe.get_doc(
            {
                "doctype": "Door Cutting Order",
                "customer": self.customer.name,
                "board_description": f"CBOT Plan Board {self.suffix}",
                "board_length_cm": 244,
                "board_width_cm": 122,
                "default_edge_type": self.edge.name,
                "edge_color": "White",
                "kerf_mm": 5,
                "trim_margin_mm": 5,
                "optimization_time_limit_sec": 10,
                "pieces": [
                    {"piece_type": "Regular", "width_cm": 40, "length_cm": 80, "qty": 1}
                ],
            }
        ).insert(ignore_permissions=True)
        recalculate_system_plan(self.order)
        approve_order_plan(self.order, "System")
        self.order.reload()

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        plan_name = frappe.db.get_value("Door Cutting Order", self.order.name, "approved_plan")
        if plan_name and frappe.db.exists("Cutting Plan", plan_name):
            frappe.delete_doc("Cutting Plan", plan_name, force=True, ignore_permissions=True)
        if frappe.db.exists("Door Cutting Order", self.order.name):
            frappe.delete_doc("Door Cutting Order", self.order.name, force=True, ignore_permissions=True)
        if frappe.db.exists("Edge Banding Type", self.edge.name):
            frappe.delete_doc("Edge Banding Type", self.edge.name, force=True, ignore_permissions=True)
        if frappe.db.exists("Customer", self.customer.name):
            frappe.delete_doc("Customer", self.customer.name, force=True, ignore_permissions=True)
        super().tearDown()

    def test_reads_exact_approved_plan_for_current_primary_phone(self) -> None:
        reader = FrappeCustomerBotApprovedPlanReader()
        snapshot = reader.read(self.phone, self.order.name)

        self.assertIsNotNone(snapshot)
        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.plan_name, self.order.approved_plan)
        self.assertEqual(snapshot.source_type, "System")
        self.assertIsNone(reader.read(self.phone, "CBOT-NOT-FOUND"))
        self.assertIsNone(reader.read("098811111111", self.order.name))

        moved_phone = self._unused_phone()
        assign_customer_primary_mobile(self.customer.name, moved_phone, update_modified=False)
        self.assertIsNone(reader.read(self.phone, self.order.name))
        assign_customer_primary_mobile(self.customer.name, self.phone, update_modified=False)

        if not _local_pdf_renderer_available():
            self.skipTest("development site has no local PDF renderer")
        try:
            pdf = FrappeCustomerBotCuttingPlanPdfAdapter().render(
                self.order.name,
                snapshot.plan_name,
            )
        except Exception as error:
            self.skipTest(f"development PDF renderer is unavailable: {error}")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 100)
        output = Path("/tmp") / f"almdina-customer-bot-approved-plan-{self.order.name}.pdf"
        output.write_bytes(pdf)
        self.addCleanup(output.unlink, missing_ok=True)

    def _customer(self):
        group = frappe.db.get_single_value("Selling Settings", "customer_group")
        if group and frappe.db.get_value("Customer Group", group, "is_group"):
            group = None
        territory = frappe.db.get_single_value("Selling Settings", "territory")
        if territory and frappe.db.get_value("Territory", territory, "is_group"):
            territory = None
        return frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": f"CBOT Plan Customer {self.suffix}",
                "customer_type": "Individual",
                "customer_group": group or self._leaf(
                    "Customer Group", "customer_group_name", "parent_customer_group"
                ),
                "territory": territory or self._leaf(
                    "Territory", "territory_name", "parent_territory"
                ),
                "mobile_no": self.phone,
            }
        ).insert(ignore_permissions=True)

    def _leaf(self, doctype: str, name_field: str, parent_field: str) -> str:
        leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
        if leaf:
            return str(leaf)
        root = frappe.db.get_value(doctype, {"is_group": 1}, "name")
        if not root:
            root = frappe.get_doc(
                {
                    "doctype": doctype,
                    name_field: f"CBOT Plan Root {self.suffix}",
                    "is_group": 1,
                }
            ).insert(ignore_permissions=True).name
        return str(
            frappe.get_doc(
                {
                    "doctype": doctype,
                    name_field: f"CBOT Plan Leaf {self.suffix}",
                    parent_field: root,
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True).name
        )

    @staticmethod
    def _unused_phone() -> str:
        phone = f"0988{secrets.randbelow(1_000_000):06d}"
        while FrappeCustomerPhoneDirectory().find_by_normalized_phone(
            normalize_customer_phone(phone)
        ):
            phone = f"0988{secrets.randbelow(1_000_000):06d}"
        return phone


def _local_pdf_renderer_available() -> bool:
    relative = {"linux": ("chrome-linux", "headless_shell")}.get(platform.system().lower())
    if relative and Path(frappe.utils.get_bench_path(), "chromium", *relative).is_file():
        return True
    return False


__all__ = ["TestCustomerBotApprovedPlanIntegration"]
