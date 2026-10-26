"""Development-site proof for an isolated order-measurements customer-bot read."""

from __future__ import annotations

import platform
import secrets
from pathlib import Path
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerServiceRequest,
)
from almdina_erp.almdina_erp.application.customer_bot.measurements_service import (
    CustomerBotMeasurementsService,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotService,
    ServiceResultCode,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import normalize_customer_phone
from almdina_erp.almdina_erp.domain.orders.revisions import RevisionState
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_measurements_pdf import (
    FrappeCustomerBotMeasurementsPdfAdapter,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_measurements_reader import (
    FrappeCustomerBotMeasurementsReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_services import (
    build_customer_bot_services,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)


class TestCustomerBotMeasurementsIntegration(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        frappe.local.lang = "ar"
        self.suffix = uuid4().hex[:10]
        self.phone = self._unused_phone()
        self.customer = self._customer()
        self.edge = self._edge_type()
        self.simple = self._order(
            "simple",
            [
                {
                    "piece_type": "Regular",
                    "width_cm": 41.5,
                    "length_cm": 80,
                    "qty": 2,
                    "edge_long_right": 1,
                    "edge_long_right_type_override": self.edge.name,
                    "notes": "مقبض علوي",
                },
                {
                    "piece_type": "Special",
                    "width_cm": 63.25,
                    "length_cm": 120.5,
                    "qty": 1,
                    "notes": "بدون إطار",
                    "special_shape_drawing_json": _door_drawing(632, 1205),
                },
            ],
        )
        self._store_addons(
            self.simple.pieces[1].name,
            {"extra_double": 1, "extra_liner": 1},
        )
        self.multipage = self._order("multipage", self._many_pieces())
        for index, piece in enumerate(self.multipage.pieces):
            self._store_addons(piece.name, self._addon_flags(index))
        self.secret = "98765.43"
        self.internal = f"INTERNAL-NOTE-{self.suffix}"
        for order in (self.simple, self.multipage):
            frappe.db.set_value(
                "Door Cutting Order",
                order.name,
                "important_note_comment",
                self.internal,
                update_modified=False,
            )
            frappe.db.set_value(
                "Door Cutting Order Detail",
                order.pieces[0].name,
                "extra_double_unit_price_usd",
                self.secret,
                update_modified=False,
            )

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for order in (getattr(self, "multipage", None), getattr(self, "simple", None)):
            if order is not None and frappe.db.exists("Door Cutting Order", order.name):
                frappe.delete_doc(
                    "Door Cutting Order", order.name, force=True, ignore_permissions=True
                )
        if getattr(self, "edge", None) and frappe.db.exists("Edge Banding Type", self.edge.name):
            frappe.delete_doc("Edge Banding Type", self.edge.name, force=True, ignore_permissions=True)
        if getattr(self, "customer", None) and frappe.db.exists("Customer", self.customer.name):
            frappe.delete_doc("Customer", self.customer.name, force=True, ignore_permissions=True)
        grant = getattr(self, "grant_name", None)
        if grant:
            frappe.db.sql(
                "delete from `tabCustomer Bot Phone Access` where name=%s",
                (grant,),
            )
        super().tearDown()

    def test_saved_measurements_follow_ownership_and_do_not_change_the_order(self) -> None:
        reader = FrappeCustomerBotMeasurementsReader()
        self.assertEqual(self.simple.price_approval_status, "Unapproved")
        self.assertFalse(self.simple.approved_plan)
        modified = frappe.db.get_value("Door Cutting Order", self.simple.name, "modified")

        snapshot = reader.read(self.phone, self.simple.name)
        self.assertIsNotNone(snapshot)
        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.order_name, self.simple.name)
        self.assertEqual(
            frappe.db.get_value("Door Cutting Order", self.simple.name, "modified"),
            modified,
        )

        missing = self._service_result(reader, "CBOT-NO-SUCH")
        foreign_phone = self._unused_phone()
        foreign = self._service_result(reader, self.simple.name, phone=foreign_phone)
        self.assertEqual(missing.code, foreign.code)
        self.assertEqual(missing.documents, ())
        self.assertEqual(foreign.documents, ())
        self.assertEqual(missing.code, ServiceResultCode.MEASUREMENTS_UNAVAILABLE)

        grant_phone = self._unused_phone()
        self.grant_name = f"CBOT-GRANT-{self.suffix}"
        frappe.db.sql(
            """insert into `tabCustomer Bot Phone Access`
               (name, customer, normalized_phone, status, creation, modified, modified_by, owner)
               values (%s, %s, %s, 'Active', now(), now(), 'Administrator', 'Administrator')""",
            (
                self.grant_name,
                self.customer.name,
                normalize_customer_phone(grant_phone),
            ),
        )
        self.assertIsNone(reader.read(grant_phone, self.simple.name))

        moved = self._unused_phone()
        frappe.db.set_value(
            "Customer", self.customer.name, "mobile_no", moved, update_modified=False
        )
        self.assertIsNone(reader.read(self.phone, self.simple.name))
        frappe.db.set_value(
            "Customer", self.customer.name, "mobile_no", self.phone, update_modified=False
        )

        frappe.db.set_value(
            "Door Cutting Order",
            self.simple.name,
            "revision_state",
            RevisionState.SUPERSEDED,
            update_modified=False,
        )
        self.assertIsNone(reader.read(self.phone, self.simple.name))
        frappe.db.set_value(
            "Door Cutting Order",
            self.simple.name,
            {"status": "Delivered", "revision_state": RevisionState.SUPERSEDED},
            update_modified=False,
        )
        delivered = reader.read(self.phone, self.simple.name)
        self.assertIsNotNone(delivered)
        self.assertEqual(delivered.order_name, self.simple.name)
        frappe.db.set_value(
            "Door Cutting Order",
            self.simple.name,
            {"status": "Cancelled", "revision_state": RevisionState.CURRENT},
            update_modified=False,
        )
        calls: list[str] = []

        class _CountingPdf:
            def render(self, phone: str, order_name: str) -> bytes:
                calls.append(order_name)
                return b"%PDF-should-not-run"

        cancelled = CustomerBotMeasurementsService(reader, _CountingPdf()).execute(
            CustomerServiceRequest(
                phone=self.phone,
                service_id=BotService.MEASUREMENTS,
                order_name=self.simple.name,
            )
        )
        self.assertEqual(cancelled.code, ServiceResultCode.MEASUREMENTS_UNAVAILABLE)
        self.assertEqual(calls, [])
        frappe.db.set_value(
            "Door Cutting Order",
            self.simple.name,
            "status",
            "Draft",
            update_modified=False,
        )

        piece_name = self.simple.pieces[0].name

        class _MutatingPdf:
            def render(self, phone: str, order_name: str) -> bytes:
                frappe.db.set_value(
                    "Door Cutting Order Detail",
                    piece_name,
                    "width_cm",
                    77.25,
                    update_modified=False,
                )
                return b"%PDF-stale"

        changed = CustomerBotMeasurementsService(reader, _MutatingPdf()).execute(
            CustomerServiceRequest(
                phone=self.phone,
                service_id=BotService.MEASUREMENTS,
                order_name=self.simple.name,
            )
        )
        self.assertEqual(changed.code, ServiceResultCode.MEASUREMENTS_DATA_CHANGED)
        self.assertEqual(changed.documents, ())
        frappe.db.set_value(
            "Door Cutting Order Detail",
            piece_name,
            "width_cm",
            41.5,
            update_modified=False,
        )
        self.assertEqual(
            frappe.db.get_value("Door Cutting Order", self.simple.name, "modified"),
            modified,
        )

        if not _local_pdf_renderer_available():
            self.fail("development site Chromium is not available for measurements PDF")
        result = build_customer_bot_services().execute(
            CustomerServiceRequest(
                phone=self.phone,
                service_id=BotService.MEASUREMENTS,
                order_name=self.simple.name,
            )
        )
        self.assertEqual(result.code, ServiceResultCode.MEASUREMENTS_READY)
        self.assertIsNone(result.amount)
        pdf = result.documents[0].content
        self._assert_real_pdf(
            pdf,
            ("41.5", "63.25"),
            arabic=(
                "دبل ضلع",
                "جدول قياسات الطلب",
                "تسليم مع المفصلات",
                "مقبض علوي",
                "رسمة الدرفة",
                self.edge.edge_type_name,
            ),
        )
        self._assert_dimension_columns(pdf, (("41.5", "80"), ("63.25", "120.5")))
        self._assert_no_letter_stack(pdf)
        self.assertNotIn(self.secret.encode(), pdf)
        self.assertNotIn(self.internal.encode(), pdf)
        self.assertEqual(
            frappe.db.get_value("Door Cutting Order", self.simple.name, "modified"),
            modified,
        )

        many = build_customer_bot_services().execute(
            CustomerServiceRequest(
                phone=self.phone,
                service_id=BotService.MEASUREMENTS,
                order_name=self.multipage.name,
            )
        )
        self.assertEqual(many.code, ServiceResultCode.MEASUREMENTS_READY)
        widths = [self._printed_number(row["width_cm"]) for row in self._many_pieces()]
        stored_double = frappe.db.get_value(
            "Door Cutting Order Detail",
            self.multipage.pieces[0].name,
            "extra_double",
        )
        self.assertEqual(int(stored_double or 0), 1)
        text = self._pdf_text(many.documents[0].content)
        folded = "".join(text.split())
        self.assertGreaterEqual(self._page_count(many.documents[0].content), 2)
        self._assert_dimension_columns(
            many.documents[0].content,
            (("20.25", "50"), ("43.75", "97")),
        )
        self._assert_no_letter_stack(many.documents[0].content)
        for width in widths:
            self.assertIn(width, folded)
        self.assertNotIn(self.secret, text)
        self.assertNotIn(self.internal, text)
        for token in ("دبل ضلع", "لاينر", "فرزة ظهر", "حفر مسكة غطس", "دبل كامل الدرفة"):
            self._assert_arabic(many.documents[0].content, text, token)
        folder = Path("/tmp/almdina-customer-bot-measurements")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "simple-measurements.pdf").write_bytes(pdf)
        (folder / "multipage-measurements.pdf").write_bytes(many.documents[0].content)

    def _service_result(self, reader, order_name: str, phone: str | None = None):
        return CustomerBotMeasurementsService(
            reader, FrappeCustomerBotMeasurementsPdfAdapter()
        ).execute(
            CustomerServiceRequest(
                phone=phone or self.phone,
                service_id=BotService.MEASUREMENTS,
                order_name=order_name,
            )
        )

    def _order(self, label: str, pieces: list[dict]):
        return frappe.get_doc(
            {
                "doctype": "Door Cutting Order",
                "customer": self.customer.name,
                "board_description": "MDF أبيض 18 مم",
                "board_length_cm": 244,
                "board_width_cm": 122,
                "default_edge_type": self.edge.name,
                "edge_color": "أبيض",
                "order_cutting_machine": "CNC",
                "order_notes": "تسليم مع المفصلات" if label == "simple" else "تجهيز المطبخ",
                "pieces": pieces,
            }
        ).insert(ignore_permissions=True)

    def _many_pieces(self) -> list[dict]:
        types = ("Regular", "Special", "Clipped Corner", "L-Shaped Corner", "Glass")
        rows = []
        for index in range(48):
            width = 20 + (index // 2) + (0.25 if index % 2 == 0 else 0.75)
            piece_type = types[index % len(types)]
            row = {
                "piece_type": piece_type,
                "width_cm": width,
                "length_cm": 50 + index,
                "qty": 1 + (index % 3),
                "notes": ("باب دولاب", "درج", "رف علوي", "جانب", "ظهر")[index % 5],
            }
            if piece_type == "Glass":
                row["glass_margin_mm"] = 20
            if piece_type == "Special" and index == 1:
                row["special_shape_drawing_json"] = _door_drawing(400, 900)
            if index % 2 and piece_type not in {"Special", "Glass"}:
                row.update(
                    {
                        "edge_width_top": 1,
                        "edge_long_left": 1,
                        "edge_long_left_type_override": self.edge.name,
                    }
                )
            rows.append(row)
        return rows

    def _assert_real_pdf(
        self,
        pdf: bytes,
        tokens: tuple[str, ...],
        arabic: tuple[str, ...] = (),
    ) -> None:
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)
        text = self._pdf_text(pdf)
        folded = "".join(text.split())
        self.assertGreaterEqual(self._page_count(pdf), 1)
        for token in tokens:
            self.assertIn("".join(token.split()), folded)
        for token in arabic:
            self._assert_arabic(pdf, text, token)

    def _assert_arabic(self, pdf: bytes, text: str, token: str) -> None:
        import unicodedata

        folded = unicodedata.normalize("NFKC", "".join(text.split()))
        if "".join(token.split()) in folded or token.encode("utf-16-be") in pdf:
            return
        self.fail(f"Arabic text was not found in the PDF: {token}")

    @staticmethod
    def _addon_flags(index: int) -> dict[str, int]:
        flags = {
            "extra_liner": 1 if index % 3 == 0 else 0,
            "extra_back_groove": 1 if index % 4 == 0 else 0,
            "extra_recessed_handle_cutout": 1 if index % 6 == 0 else 0,
            "extra_double": 0,
            "extra_full_door_double": 0,
        }
        if index % 2 == 0:
            flags["extra_double"] = 1
        elif index % 5 == 0:
            flags["extra_full_door_double"] = 1
        return flags

    @staticmethod
    def _store_addons(piece_name: str, flags: dict[str, int]) -> None:
        frappe.db.set_value(
            "Door Cutting Order Detail",
            piece_name,
            flags,
            update_modified=False,
        )

    @staticmethod
    def _printed_number(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    @staticmethod
    def _pdf_text(pdf: bytes) -> str:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(pdf))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def _page_count(pdf: bytes) -> int:
        from pypdf import PdfReader
        import io

        return len(PdfReader(io.BytesIO(pdf)).pages)

    def _customer(self):
        return _new_customer(self.phone, "ليان درويش")

    def _edge_type(self):
        for label, english in (
            ("ذهبي", "Gold"),
            ("سنديان", "Oak"),
            ("خشبي فاتح", "Light wood"),
            ("أبيض لامع", "Gloss white"),
        ):
            if not frappe.db.exists("Edge Banding Type", label):
                return frappe.get_doc(
                    {
                        "doctype": "Edge Banding Type",
                        "edge_type_name": label,
                        "english_name": english,
                        "width_cm": 2,
                        "thickness_mm": 1,
                        "rate_usd_per_meter": 1,
                    }
                ).insert(ignore_permissions=True)
        self.fail("no free realistic edge name")

    def _assert_dimension_columns(self, pdf: bytes, pairs: tuple[tuple[str, str], ...]) -> None:
        placed = TestCustomerBotMeasurementsIntegration._text_positions(pdf)
        for width, length in pairs:
            matched = any(
                abs(width_y - length_y) <= 4 and abs(width_x - length_x) >= 30
                for width_x, width_y, width_text in placed
                if width_text == width
                for length_x, length_y, length_text in placed
                if length_text == length
            )
            self.assertTrue(matched, f"width {width} and length {length} are not in separate columns")

    def _assert_no_letter_stack(self, pdf: bytes) -> None:
        runs = TestCustomerBotMeasurementsIntegration._text_positions(pdf)
        streak = 1
        for earlier, later in zip(runs, runs[1:]):
            earlier_x, earlier_y, earlier_text = earlier
            later_x, later_y, later_text = later
            stacked = (
                len(earlier_text) == 1
                and len(later_text) == 1
                and abs(earlier_x - later_x) <= 2
                and 8 <= earlier_y - later_y <= 14
            )
            streak = streak + 1 if stacked else 1
            self.assertLess(streak, 4, "text wraps one letter under the next")

    @staticmethod
    def _text_positions(pdf: bytes) -> list[tuple[float, float, str]]:
        from pypdf import PdfReader
        import io

        placed: list[tuple[float, float, str]] = []

        def visit(text, cm, tm, _font_dict, _font_size):
            token = "".join(str(text or "").split())
            if not token:
                return
            a_scale, _b, c_scale, _d, origin_x, origin_y = cm
            placed.append(
                (
                    round(a_scale * tm[4] + c_scale * tm[5] + origin_x, 1),
                    round(_b * tm[4] + _d * tm[5] + origin_y, 1),
                    token,
                )
            )

        for page in PdfReader(io.BytesIO(pdf)).pages:
            page.extract_text(visitor_text=visit)
        return placed

    @staticmethod
    def _unused_phone() -> str:
        phone = f"0988{secrets.randbelow(1_000_000):06d}"
        while FrappeCustomerPhoneDirectory().find_by_normalized_phone(
            normalize_customer_phone(phone)
        ):
            phone = f"0988{secrets.randbelow(1_000_000):06d}"
        return phone


def _new_customer(phone: str, customer_name: str):
    group = frappe.db.get_single_value("Selling Settings", "customer_group")
    if not group or frappe.db.get_value("Customer Group", group, "is_group"):
        group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
    territory = frappe.db.get_single_value("Selling Settings", "territory")
    if not territory or frappe.db.get_value("Territory", territory, "is_group"):
        territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
    return frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": "Individual",
            "customer_group": group,
            "territory": territory,
            "mobile_no": phone,
        }
    ).insert(ignore_permissions=True)


def _door_drawing(width_mm: int, height_mm: int) -> str:
    inner_width = max(1, width_mm - 40)
    inner_height = max(1, height_mm - 40)
    return (
        '{"schema":"almdina.special-shape-documentation","version":1,'
        f'"canvas":{{"widthMm":{width_mm},"heightMm":{height_mm}}},'
        '"elements":[{"id":"frame","type":"rect","xMm":20,"yMm":20,'
        f'"widthMm":{inner_width},"heightMm":{inner_height}}}],'
        '"source":"mixed"}'
    )


class TestCustomerBotMeasurementsLongText(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        frappe.local.lang = "ar"
        self.phone = TestCustomerBotMeasurementsIntegration._unused_phone()
        self.customer = _new_customer(self.phone, "هدى قاسم")
        self.edge_name = "شريط أبيض لامع للخزائن العلوية"
        if frappe.db.exists("Edge Banding Type", self.edge_name):
            self.edge_name = "شريط سنديان للخزائن السفلية بعرض سنتيمترين"
        self.edge = frappe.get_doc(
            {
                "doctype": "Edge Banding Type",
                "edge_type_name": self.edge_name,
                "english_name": "Cabinet edge",
                "width_cm": 2,
                "thickness_mm": 1,
                "rate_usd_per_meter": 1,
            }
        ).insert(ignore_permissions=True)
        self.note = "يرجى تثبيت المقبض في الأعلى مع إبقاء مسافة عن الحافة وتغليف القطعة قبل التسليم"
        self.order = frappe.get_doc(
            {
                "doctype": "Door Cutting Order",
                "customer": self.customer.name,
                "board_description": "MDF أبيض 18 مم",
                "board_length_cm": 244,
                "board_width_cm": 122,
                "default_edge_type": self.edge.name,
                "edge_color": "أبيض",
                "order_cutting_machine": "CNC",
                "order_notes": "تسليم مغلف",
                "pieces": [
                    {
                        "piece_type": "Regular",
                        "width_cm": 55,
                        "length_cm": 90,
                        "qty": 1,
                        "edge_long_right": 1,
                        "edge_long_right_type_override": self.edge.name,
                        "notes": self.note,
                    }
                ],
            }
        ).insert(ignore_permissions=True)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        if getattr(self, "order", None) and frappe.db.exists("Door Cutting Order", self.order.name):
            frappe.delete_doc("Door Cutting Order", self.order.name, force=True, ignore_permissions=True)
        if getattr(self, "edge", None) and frappe.db.exists("Edge Banding Type", self.edge.name):
            frappe.delete_doc("Edge Banding Type", self.edge.name, force=True, ignore_permissions=True)
        if getattr(self, "customer", None) and frappe.db.exists("Customer", self.customer.name):
            frappe.delete_doc("Customer", self.customer.name, force=True, ignore_permissions=True)
        super().tearDown()

    def test_long_customer_text_stays_in_words(self) -> None:
        if not _local_pdf_renderer_available():
            self.fail("development site Chromium is not available for measurements PDF")
        result = build_customer_bot_services().execute(
            CustomerServiceRequest(
                phone=self.phone,
                service_id=BotService.MEASUREMENTS,
                order_name=self.order.name,
            )
        )
        self.assertEqual(result.code, ServiceResultCode.MEASUREMENTS_READY)
        pdf = result.documents[0].content
        text = TestCustomerBotMeasurementsIntegration._pdf_text(pdf)
        TestCustomerBotMeasurementsIntegration._assert_arabic(self, pdf, text, self.note)
        TestCustomerBotMeasurementsIntegration._assert_arabic(self, pdf, text, self.edge_name)
        TestCustomerBotMeasurementsIntegration._assert_dimension_columns(self, pdf, (("55", "90"),))
        TestCustomerBotMeasurementsIntegration._assert_no_letter_stack(self, pdf)
        self.assertNotIn(b"98765.43", pdf)


def _local_pdf_renderer_available() -> bool:
    relative = {"linux": ("chrome-linux", "headless_shell")}.get(platform.system().lower())
    if relative and Path(frappe.utils.get_bench_path(), "chromium", *relative).is_file():
        return True
    return False


__all__ = [
    "TestCustomerBotMeasurementsIntegration",
    "TestCustomerBotMeasurementsLongText",
]
