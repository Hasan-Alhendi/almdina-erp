"""Approved-price invoice through Chromium and the reply-intent path.

The order, cost inputs, and approval are created here. Approval goes through
the official final-price service with the current basis token. Nothing is sent
to a live gateway.
"""

from __future__ import annotations

import io
import platform
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from pypdf import PdfReader

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerBotServiceRouter,
)
from almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents import (
    ReplyDeliveryDeps,
    deliver_one_reply,
)
from almdina_erp.almdina_erp.application.customer_bot.final_price_service import (
    CustomerBotFinalPriceService,
)
from almdina_erp.almdina_erp.domain.customer_bot.gateway_capabilities import BotGatewayCapabilities
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import normalize_customer_phone
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import CANCELLED
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import PROCESSED
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import SendDisposition, TextSendResult
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    fingerprint_final_price_basis,
    price_basis_token,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_final_price_reader import (
    FrappeCustomerBotFinalPriceReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_invoice_pdf import (
    FrappeCustomerBotInvoicePdfAdapter,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_order_reader import (
    FrappeCustomerOrderReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository import (
    FrappeCustomerBotReplyRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_session_repository import (
    FrappeCustomerBotSessionRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.frappe.final_price_approval_gateway import (
    FrappeFinalPriceApprovalGateway,
)
from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
    approve_order_plan,
    recalculate_system_plan,
)
from almdina_erp.almdina_erp.services.cutting_plan_cost_command_service import (
    update_plan_cost_settings,
)
from almdina_erp.almdina_erp.services.final_price_approval_service import (
    approve_order_final_price,
    cancel_order_final_price_approval,
)
from almdina_erp.tests.test_customer_bot_inbound_session import _Settings

PREFIX = "cbot-inv-"
_INTERNAL_MARKERS = (
    "internal_cost_report",
    "تقرير التكلفة الداخلي",
    "هامش الربح",
    "داخلي — لا يسلّم للزبون",
    "تكلفة ألواح MDF",
)


class _CountingPdf:
    def __init__(self) -> None:
        self.inner = FrappeCustomerBotInvoicePdfAdapter()
        self.calls = 0
        self.last = b""

    def render(self, order_name: str, invoice_payload) -> bytes:
        self.calls += 1
        self.last = self.inner.render(order_name, invoice_payload)
        return self.last


class _TextPort:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def capabilities(self) -> BotGatewayCapabilities:
        return BotGatewayCapabilities(True, False, False)

    def send_text_reply(self, request):
        self.calls.append(request.text)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="fake-text",
            reason_code="gateway_accepted",
        )


class _DocumentPort:
    def __init__(self) -> None:
        self.contents: list[bytes] = []
        self.captions: list[str] = []

    def send_document_reply(self, request):
        self.contents.append(request.content)
        self.captions.append(request.caption)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="fake-document",
            reason_code="gateway_accepted",
        )


class TestCustomerBotFinalPriceIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.suffix = uuid4().hex[:10]
        self.connection = PREFIX + self.suffix
        self.local_phone = self._unused_local_phone()
        self.phone = normalize_customer_phone(self.local_phone)
        self.customer = self._customer()
        self.edge = frappe.get_doc(
            {
                "doctype": "Edge Banding Type",
                "edge_type_name": f"CBOT Price Edge {self.suffix}",
                "english_name": f"CBOT Price Edge {self.suffix}",
                "width_cm": 2,
                "thickness_mm": 1,
                "rate_usd_per_meter": 1,
            }
        ).insert(ignore_permissions=True)
        self.order = frappe.get_doc(
            {
                "doctype": "Door Cutting Order",
                "customer": self.customer.name,
                "board_description": f"CBOT Price Board {self.suffix}",
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
        update_plan_cost_settings(
            self.order,
            board_rate_usd=25,
            cutting_cost_per_board_usd=4,
            offcut_price_usd=0,
        )
        self.order.reload()
        self.now = datetime.now(timezone.utc)
        self.settings = _Settings()
        self.directory = FrappeCustomerPhoneDirectory()
        self.orders = FrappeCustomerOrderReader()
        self.sessions = FrappeCustomerBotSessionRepository()
        self.outbox = FrappeCustomerBotReplyRepository()
        self.pdf = _CountingPdf()
        self.services = CustomerBotServiceRouter(
            CustomerBotFinalPriceService(FrappeCustomerBotFinalPriceReader(), self.pdf)
        )
        self.text = _TextPort()
        self.documents = _DocumentPort()
        self._decision_before = frappe.db.get_single_value(
            "Customer Bot Settings", "operation_decision"
        )

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        self._cleanup()
        super().tearDown()

    def test_approved_invoice_is_rendered_once_and_a_cancelled_approval_is_not_sent(self) -> None:
        self.assertTrue(_local_pdf_renderer_available(), "local Chromium PDF renderer is missing")
        gateway = FrappeFinalPriceApprovalGateway()
        plan = gateway.resolve_cost_plan(self.order)
        self.assertIsNotNone(plan)
        basis = gateway.build_basis_payload(self.order, plan)
        fingerprint = fingerprint_final_price_basis(basis)
        token = price_basis_token(
            fingerprint,
            formula_version=str(basis.get("formula_version") or ""),
        )
        approved = approve_order_final_price(self.order.name, token, "phase5 invoice proof")
        self.assertEqual(approved["price_approval_status"], "Approved")
        self.assertEqual(approved["price_basis_token"], token)
        self.assertEqual(approved["pricing_basis_fingerprint"], fingerprint)
        self.assertEqual(approved["currency"], "USD")
        self.assertGreater(Decimal(str(approved["approved_amount_usd"])), Decimal("0"))
        self.order.reload()

        snapshot = FrappeCustomerBotFinalPriceReader().read(self.phone, self.order.name)
        self.assertIsNotNone(snapshot)
        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.currency, "USD")
        self.assertEqual(
            snapshot.amount,
            Decimal(str(approved["approved_amount_usd"])).quantize(Decimal("0.01")),
        )
        self.assertEqual(snapshot.invoice_payload["kind"], "customer_invoice")
        self.assertNotIn("internal_cost_report", snapshot.invoice_payload)
        payload_text = frappe.as_json(snapshot.invoice_payload)
        for marker in _INTERNAL_MARKERS:
            self.assertNotIn(marker, payload_text)
        self.assertIsNone(FrappeCustomerBotFinalPriceReader().read(self.phone, "CBOT-NOT-FOUND"))
        self.assertIsNone(
            FrappeCustomerBotFinalPriceReader().read("+963988000000", self.order.name)
        )

        described = self._accept("2", "e-price")
        self.assertEqual(described.disposition, PROCESSED)
        self.assertEqual(self.pdf.calls, 0)
        self.assertEqual(len(described.documents), 1)

        sent = self._deliver()
        self.assertIsNotNone(sent)
        self.assertEqual(sent.status, SendDisposition.ACCEPTED.value)
        self.assertEqual(self.pdf.calls, 1)
        self.assertEqual(len(self.documents.contents), 1)
        self.assertTrue(self.documents.contents[0].startswith(b"%PDF"))
        self.assertGreater(len(self.documents.contents[0]), 100)
        self.assertEqual(self.documents.contents[0], self.pdf.last)
        caption = self.documents.captions[0]
        amount = f"{snapshot.amount:.2f}"
        self.assertIn(self.order.name, caption)
        self.assertIn(amount, caption)
        self.assertIn("USD", caption)
        for marker in _INTERNAL_MARKERS:
            self.assertNotIn(marker, caption)
        self.assertEqual(snapshot.invoice_payload["title"], "عرض سعر الطلب")
        extracted = _pdf_text(self.documents.contents[0])
        self.assertIn("Quotation details", extracted)
        self.assertIn(f"Final total $ {amount}", extracted)
        for marker in _INTERNAL_MARKERS:
            self.assertNotIn(marker, extracted)
            self.assertNotIn(marker[::-1], extracted)
        self.assertNotIn(amount, "".join(self.text.calls))

        menu = self._accept("0", "e-menu")
        self.assertEqual(menu.disposition, PROCESSED)
        self.assertEqual(self.pdf.calls, 1)
        menu_sent = self._deliver()
        self.assertEqual(menu_sent.status, SendDisposition.ACCEPTED.value)
        self.assertEqual(self.pdf.calls, 1)
        self.assertEqual(len(self.documents.contents), 1)

        again = self._accept("2", "e-price-again")
        self.assertEqual(again.disposition, PROCESSED)
        self.assertEqual(len(again.documents), 1)
        self.assertEqual(self.pdf.calls, 1)
        cancelled = cancel_order_final_price_approval(
            self.order.name,
            approved["current_price_approval"],
        )
        self.assertEqual(cancelled["price_approval_status"], "Unapproved")
        self.assertTrue(cancelled["cancelled_now"])
        blocked = self._deliver()
        self.assertEqual(blocked.status, CANCELLED)
        self.assertEqual(self.pdf.calls, 1)
        self.assertEqual(len(self.documents.contents), 1)
        self.assertEqual(len(self.documents.captions), 1)
        self.assertNotIn(amount, "".join(self.text.calls))
        self.assertEqual(
            frappe.db.get_single_value("Customer Bot Settings", "operation_decision"),
            self._decision_before,
        )
        self.assertEqual(self._decision_before, "stopped")

    def _accept(self, text: str, event: str):
        return accept_inbound_customer_message(
            build_inbound_customer_message(
                connection_ref=self.connection,
                provider_event_id=event,
                conversation_id=self.connection + "-chat",
                sender_id=self.connection + "-sender",
                occurred_at=self.now,
                kind=InboundMessageKind.TEXT,
                text=text,
                from_own_account=False,
                is_group=False,
                trusted_normalized_phone=self.phone,
            ),
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=self.orders,
            stages=self.orders,
            routes=self.orders,
            services=self.services,
            now=self.now,
        )

    def _deliver(self):
        return deliver_one_reply(
            self.outbox,
            self.text,
            deps=ReplyDeliveryDeps(
                settings=self.settings,
                directory=self.directory,
                services=self.services,
                document_port=self.documents,
            ),
            now=self.now,
            eligible_phone=self.phone,
        )

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
                "customer_name": f"CBOT Price Customer {self.suffix}",
                "customer_type": "Individual",
                "customer_group": group or self._leaf(
                    "Customer Group", "customer_group_name", "parent_customer_group"
                ),
                "territory": territory or self._leaf(
                    "Territory", "territory_name", "parent_territory"
                ),
                "mobile_no": self.local_phone,
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
                    name_field: f"CBOT Price Root {self.suffix}",
                    "is_group": 1,
                }
            ).insert(ignore_permissions=True).name
        return str(
            frappe.get_doc(
                {
                    "doctype": doctype,
                    name_field: f"CBOT Price Leaf {self.suffix}",
                    parent_field: root,
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True).name
        )

    def _unused_local_phone(self) -> str:
        directory = FrappeCustomerPhoneDirectory()
        while True:
            local = f"0988{secrets.randbelow(1_000_000):06d}"
            if not directory.find_by_normalized_phone(normalize_customer_phone(local)):
                return local

    def _cleanup(self) -> None:
        frappe.db.rollback()
        order_name = getattr(getattr(self, "order", None), "name", None)
        if order_name:
            frappe.db.sql(
                "delete from `tabDoor Cutting Price Approval` where door_cutting_order=%s",
                (order_name,),
            )
            plans = frappe.get_all(
                "Cutting Plan",
                filters={"door_cutting_order": order_name},
                pluck="name",
            )
            for plan_name in plans:
                if frappe.db.exists("Cutting Plan", plan_name):
                    frappe.delete_doc(
                        "Cutting Plan", plan_name, force=True, ignore_permissions=True
                    )
            if frappe.db.exists("Door Cutting Order", order_name):
                frappe.delete_doc(
                    "Door Cutting Order", order_name, force=True, ignore_permissions=True
                )
        edge_name = getattr(getattr(self, "edge", None), "name", None)
        if edge_name and frappe.db.exists("Edge Banding Type", edge_name):
            frappe.delete_doc(
                "Edge Banding Type", edge_name, force=True, ignore_permissions=True
            )
        customer_name = getattr(getattr(self, "customer", None), "name", None)
        if customer_name and frappe.db.exists("Customer", customer_name):
            frappe.delete_doc("Customer", customer_name, force=True, ignore_permissions=True)
        connection = getattr(self, "connection", None)
        if connection:
            frappe.db.sql(
                "delete from `tabCustomer Bot Reply Intent` where connection_ref=%s",
                (connection,),
            )
            frappe.db.sql(
                "delete from `tabCustomer Bot Conversation` where connection_ref=%s",
                (connection,),
            )
            frappe.db.sql(
                "delete from `tabCustomer Bot Inbound Event` where connection_ref=%s",
                (connection,),
            )
        frappe.db.commit()


def _local_pdf_renderer_available() -> bool:
    relative = {"linux": ("chrome-linux", "headless_shell")}.get(platform.system().lower())
    if relative and Path(frappe.utils.get_bench_path(), "chromium", *relative).is_file():
        return True
    return False


def _pdf_text(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


__all__ = ["TestCustomerBotFinalPriceIntegration"]
