from __future__ import annotations

import unittest
from unittest.mock import patch

from almdina_erp.almdina_erp.application.whatsapp.errors import (
    WhatsAppError,
    WhatsAppTransportError,
)
from almdina_erp.almdina_erp.application.whatsapp.ports import (
    MessageReceipt,
    QrCode,
    WhatsAppSession,
)
from almdina_erp.almdina_erp.application.whatsapp.send_invoice import (
    invoice_filename,
    send_order_invoice,
)
from almdina_erp.almdina_erp.application.whatsapp.send_measurements import (
    measurements_text,
    send_order_measurements,
)
from almdina_erp.almdina_erp.application.whatsapp.send_stage_completion import (
    send_stage_completion,
    stage_completion_text,
)
from almdina_erp.almdina_erp.application.whatsapp.sessions import (
    create_and_start_factory_session,
    delivery_status,
    get_factory_session,
    get_session_qr,
    reconnect_factory_session,
    session_snapshot,
)
from almdina_erp.almdina_erp.domain.whatsapp.session_policy import SESSION_NAME_PREFIX


def _session(**overrides: object) -> WhatsAppSession:
    payload = {
        "id": "sid-1",
        "name": "bound-session",
        "status": "ready",
        "phone": "963944123456",
        "push_name": "Factory",
        "last_error": None,
        "engine_loaded": True,
    }
    payload.update(overrides)
    return WhatsAppSession(**payload)  # type: ignore[arg-type]


class FakeWhatsAppGateway:
    def __init__(self, sessions: list[WhatsAppSession] | None = None) -> None:
        self.sessions = list(sessions or [])
        self.started: list[str] = []
        self.listed = 0
        self.texts: list[tuple[str, str, str]] = []
        self.documents: list[tuple[str, str, str, str, bytes, str]] = []
        self.qr = QrCode(qr_code="data:image/png;base64,AAA", status="qr_ready")
        self.fail_qr = False
        self.fail_text: str | None = None
        self.fail_document: str | None = None
        self.fail_create_after_insert = False
        self.fail_start = False
        self.start_status = "qr_ready"

    def list_sessions(self) -> list[WhatsAppSession]:
        self.listed += 1
        return list(self.sessions)

    def create_session(self, name: str) -> WhatsAppSession:
        created = _session(
            id="new-sid",
            name=name,
            status="created",
            engine_loaded=False,
            phone=None,
            push_name=None,
        )
        self.sessions.append(created)
        if self.fail_create_after_insert:
            raise WhatsAppTransportError("timed out", code="timeout")
        return created

    def get_session(self, session_id: str) -> WhatsAppSession:
        for session in self.sessions:
            if session.id == session_id:
                return session
        raise WhatsAppTransportError("not found", status_code=404, code="missing")

    def start(self, session_id: str) -> WhatsAppSession:
        if self.fail_start:
            raise WhatsAppTransportError("start failed", code="timeout")
        self.started.append(session_id)
        updated = []
        current = None
        for session in self.sessions:
            if session.id != session_id:
                updated.append(session)
                continue
            current = _session(
                id=session.id,
                name=session.name,
                status=self.start_status,
                engine_loaded=True,
                phone=session.phone,
                push_name=session.push_name,
            )
            updated.append(current)
        self.sessions = updated
        assert current is not None
        return current

    def stop(self, session_id: str) -> WhatsAppSession:
        return self.get_session(session_id)

    def get_qr(self, session_id: str) -> QrCode:
        if self.fail_qr:
            raise WhatsAppTransportError("QR code not ready", status_code=400)
        return self.qr

    def send_text(self, session_id: str, chat_id: str, text: str) -> MessageReceipt:
        if self.fail_text:
            raise WhatsAppTransportError(self.fail_text, status_code=409)
        self.texts.append((session_id, chat_id, text))
        return MessageReceipt(message_id="text-1", timestamp=1)

    def send_document(
        self,
        session_id: str,
        chat_id: str,
        *,
        filename: str,
        mimetype: str,
        data: bytes,
        caption: str = "",
    ) -> MessageReceipt:
        if self.fail_document:
            raise WhatsAppTransportError(self.fail_document, status_code=409)
        self.documents.append((session_id, chat_id, filename, mimetype, data, caption))
        return MessageReceipt(message_id="doc-1", timestamp=2)


class FakeSessionStore:
    def __init__(self, session_id: str = "sid-1", session_name: str = "") -> None:
        self.session_id = session_id
        self.session_name = session_name

    def get_session_id(self) -> str:
        return self.session_id

    def save_session_id(self, session_id: str) -> None:
        self.session_id = session_id

    def get_session_name(self) -> str:
        return self.session_name

    def save_session_name(self, session_name: str) -> None:
        self.session_name = session_name


def _store(session_id: str = "sid-1", session_name: str = "") -> FakeSessionStore:
    return FakeSessionStore(session_id, session_name)


class FakePhoneGateway:
    def __init__(self, phone: str = "0944123456") -> None:
        self.phone = phone

    def get_customer_phone(self, order_name: str) -> str:
        return self.phone


class FakePdfGateway:
    def __init__(self, content: bytes = b"%PDF-fake") -> None:
        self.content = content
        self.invoice_payloads: list[object] = []

    def render_measurements_pdf(self, order_name: str) -> bytes:
        return self.content

    def render_invoice_pdf(
        self,
        order_name: str,
        invoice_payload: object = None,
    ) -> bytes:
        self.invoice_payloads.append(invoice_payload)
        return self.content


class WhatsAppSessionUseCaseTests(unittest.TestCase):
    def test_create_starts_a_unique_session_and_stores_its_name_and_id(self) -> None:
        gateway = FakeWhatsAppGateway([_session(id="other", name="almdina-taken")])
        store = _store("")
        with patch(
            "almdina_erp.almdina_erp.application.whatsapp.sessions._draw_session_token",
            side_effect=["taken", "fresh"],
        ):
            session = create_and_start_factory_session(gateway, store)
        self.assertEqual(session.name, f"{SESSION_NAME_PREFIX}fresh")
        self.assertEqual(session.id, "new-sid")
        self.assertEqual(store.get_session_id(), "new-sid")
        self.assertEqual(store.get_session_name(), f"{SESSION_NAME_PREFIX}fresh")
        self.assertEqual(gateway.started, ["new-sid"])
        self.assertEqual(gateway.listed, 1)
        self.assertTrue(session.engine_loaded)

    def test_create_reuses_the_bound_session_instead_of_a_second_one(self) -> None:
        gateway = FakeWhatsAppGateway(
            [_session(id="ours"), _session(id="other", name="dashboard")]
        )
        store = _store("ours")
        session = create_and_start_factory_session(gateway, store)
        self.assertEqual(session.id, "ours")
        self.assertEqual(gateway.started, [])
        self.assertEqual(store.get_session_id(), "ours")
        self.assertNotIn("new-sid", [item.id for item in gateway.sessions])

    def test_existing_named_session_is_started_for_qr_when_start_fails(self) -> None:
        gateway = FakeWhatsAppGateway(
            [
                _session(
                    id="orphan",
                    name="almdina-kept",
                    status="failed",
                    engine_loaded=False,
                    phone=None,
                    push_name=None,
                    last_error="start failed",
                )
            ]
        )
        gateway.fail_start = True
        store = _store("", "almdina-kept")
        session = create_and_start_factory_session(gateway, store)
        snapshot = session_snapshot(session)
        self.assertEqual(session.id, "orphan")
        self.assertEqual(store.get_session_id(), "orphan")
        self.assertEqual(gateway.started, [])
        self.assertTrue(snapshot["needs_qr"])
        self.assertFalse(snapshot["working"])
        self.assertNotIn("new-sid", [item.id for item in gateway.sessions])

    def test_create_reclaims_the_named_session_when_its_id_was_not_saved(self) -> None:
        gateway = FakeWhatsAppGateway(
            [
                _session(
                    id="orphan",
                    name="almdina-kept",
                    status="created",
                    engine_loaded=False,
                    phone=None,
                    push_name=None,
                ),
                _session(id="other", name="dashboard"),
            ]
        )
        store = _store("", "almdina-kept")
        session = create_and_start_factory_session(gateway, store)
        self.assertEqual(session.id, "orphan")
        self.assertEqual(store.get_session_id(), "orphan")
        self.assertEqual(gateway.started, ["orphan"])
        self.assertNotIn("new-sid", [item.id for item in gateway.sessions])

    def test_timed_out_create_saves_the_session_the_server_already_made(self) -> None:
        gateway = FakeWhatsAppGateway([_session(id="other", name="dashboard")])
        gateway.fail_create_after_insert = True
        store = _store("")
        with patch(
            "almdina_erp.almdina_erp.application.whatsapp.sessions._draw_session_token",
            return_value="once",
        ):
            session = create_and_start_factory_session(gateway, store)
        self.assertEqual(session.id, "new-sid")
        self.assertEqual(store.get_session_id(), "new-sid")
        self.assertEqual(store.get_session_name(), f"{SESSION_NAME_PREFIX}once")
        self.assertEqual(gateway.started, ["new-sid"])

    def test_create_does_not_guess_when_the_factory_name_is_ambiguous(self) -> None:
        gateway = FakeWhatsAppGateway(
            [
                _session(id="a", name="almdina-dup"),
                _session(id="b", name="almdina-dup"),
            ]
        )
        store = _store("", "almdina-dup")
        with self.assertRaises(WhatsAppError) as raised:
            create_and_start_factory_session(gateway, store)
        self.assertEqual(raised.exception.code, "ambiguous_session")
        self.assertEqual(store.get_session_id(), "")
        self.assertEqual(gateway.started, [])

    def test_get_factory_session_ignores_other_projects(self) -> None:
        gateway = FakeWhatsAppGateway(
            [
                _session(id="dash", name="from-ui"),
                _session(id="legacy", name="almdina-factory"),
            ]
        )
        store = _store("")
        self.assertIsNone(get_factory_session(gateway, store))
        self.assertEqual(store.get_session_id(), "")
        self.assertEqual(gateway.listed, 0)

    def test_get_factory_session_stores_the_named_session_and_exposes_qr(self) -> None:
        gateway = FakeWhatsAppGateway(
            [
                _session(id="other", name="dashboard", status="disconnected"),
                _session(
                    id="ours",
                    name="almdina-ours",
                    status="qr_ready",
                    engine_loaded=True,
                ),
            ]
        )
        store = _store("", "almdina-ours")
        session = get_factory_session(gateway, store)
        self.assertIsNotNone(session)
        self.assertEqual(session.id, "ours")
        self.assertEqual(store.get_session_id(), "ours")
        snapshot = session_snapshot(session)
        self.assertIsNotNone(snapshot["session"])
        self.assertTrue(snapshot["needs_qr"])
        payload = get_session_qr(gateway, store)
        self.assertEqual(payload["qr_code"], gateway.qr.qr_code)
        self.assertFalse(payload["working"])
        self.assertEqual(store.get_session_id(), "ours")

    def test_get_factory_session_uses_only_the_stored_id(self) -> None:
        gateway = FakeWhatsAppGateway(
            [
                _session(id="other", name="dashboard"),
                _session(id="ours", name="factory"),
            ]
        )
        session = get_factory_session(gateway, _store("ours"))
        self.assertIsNotNone(session)
        self.assertEqual(session.id, "ours")

    def test_missing_remote_session_does_not_fall_back_and_can_be_replaced(self) -> None:
        gateway = FakeWhatsAppGateway([_session(id="other", name="dashboard")])
        store = _store("gone")
        self.assertIsNone(get_factory_session(gateway, store))
        snapshot = session_snapshot(get_factory_session(gateway, store))
        self.assertTrue(snapshot["can_create"])
        self.assertEqual(snapshot["code"], "missing_session")
        created = create_and_start_factory_session(gateway, store)
        self.assertEqual(created.id, "new-sid")
        self.assertEqual(store.get_session_id(), "new-sid")
        self.assertEqual(gateway.started, ["new-sid"])

    def test_reconnect_starts_when_engine_is_down(self) -> None:
        gateway = FakeWhatsAppGateway(
            [_session(status="disconnected", engine_loaded=False)]
        )
        session = reconnect_factory_session(gateway, _store())
        self.assertEqual(gateway.started, ["sid-1"])
        self.assertEqual(session.status, "qr_ready")

    def test_qr_returns_ready_without_image_once_working(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        payload = get_session_qr(gateway, _store())
        self.assertTrue(payload["working"])
        self.assertEqual(payload["qr_code"], "")

    def test_delivery_status_reports_disconnected_session(self) -> None:
        gateway = FakeWhatsAppGateway([_session(status="disconnected")])
        status = delivery_status(gateway, _store())
        self.assertFalse(status["working"])
        self.assertEqual(status["code"], "not_ready")

    def test_snapshot_marks_unconfigured_gateway(self) -> None:
        payload = session_snapshot(None, configured=False)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["can_create"])


class WhatsAppSendMeasurementsTests(unittest.TestCase):
    def test_sends_pdf_and_text_as_one_message(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        result = send_order_measurements(
            gateway,
            FakePdfGateway(),
            FakePhoneGateway("0944123456"),
            "DCO-0001",
            session_store=_store(),
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.chat_id, "963944123456@c.us")
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents[0][2], "قياسات-DCO-0001.pdf")
        self.assertEqual(gateway.documents[0][3], "application/pdf")
        self.assertEqual(gateway.documents[0][4], b"%PDF-fake")
        self.assertEqual(gateway.documents[0][5], measurements_text("DCO-0001"))
        self.assertEqual(result.text_message_id, result.document_message_id)
        self.assertEqual(result.document_message_id, "doc-1")

    def test_missing_phone_fails_before_openwa(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        with self.assertRaises(WhatsAppError) as raised:
            send_order_measurements(
                gateway,
                FakePdfGateway(),
                FakePhoneGateway(""),
                "DCO-0001",
                session_store=_store(),
            )
        self.assertEqual(raised.exception.code, "missing_phone")
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents, [])

    def test_disconnected_session_does_not_send(self) -> None:
        gateway = FakeWhatsAppGateway([_session(status="disconnected")])
        with self.assertRaises(WhatsAppError) as raised:
            send_order_measurements(
                gateway,
                FakePdfGateway(),
                FakePhoneGateway(),
                "DCO-0001",
                session_store=_store(),
            )
        self.assertEqual(raised.exception.code, "session_not_ready")

    def test_document_failure_sends_nothing(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        gateway.fail_document = "engine reconnecting"
        with self.assertRaises(WhatsAppError) as raised:
            send_order_measurements(
                gateway,
                FakePdfGateway(),
                FakePhoneGateway(),
                "DCO-0001",
                session_store=_store(),
            )
        self.assertEqual(raised.exception.code, "send_failed")
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents, [])

    def test_caption_longer_than_whatsapp_limit_is_not_sent(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        with self.assertRaises(WhatsAppError) as raised:
            send_order_measurements(
                gateway,
                FakePdfGateway(),
                FakePhoneGateway(),
                "DCO-0001",
                text_template="م" * 1025,
                session_store=_store(),
            )
        self.assertEqual(raised.exception.code, "caption_too_long")
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents, [])

    def test_custom_text_template_is_the_document_caption(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        result = send_order_measurements(
            gateway,
            FakePdfGateway(),
            FakePhoneGateway("0944123456"),
            "DCO-0001",
            text_template="قياسات الطلب {order_name} جاهزة",
            session_store=_store(),
        )
        self.assertTrue(result.ok)
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents[0][5], "قياسات الطلب DCO-0001 جاهزة")

    def test_use_case_stays_frappe_free(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "application"
            / "whatsapp"
            / "send_invoice.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("cost_document_service", source)
        self.assertIn("format_whatsapp_preamble", source)
        self.assertIn("text_template", source)

    def test_sends_invoice_pdf_with_text_as_one_message(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        pdf = FakePdfGateway()
        payload = {
            "kind": "customer_invoice",
            "lines": [{"description": "ألواح MDF", "amount_usd": 10}],
            "totals": [{"label": "الإجمالي النهائي", "value_usd": 10}],
        }
        result = send_order_invoice(
            gateway,
            pdf,
            FakePhoneGateway("0944123456"),
            "DCO-0001",
            payload,
            session_store=_store(),
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.chat_id, "963944123456@c.us")
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents[0][2], invoice_filename("DCO-0001"))
        self.assertEqual(gateway.documents[0][4], b"%PDF-fake")
        self.assertEqual(gateway.documents[0][5], measurements_text("DCO-0001"))
        self.assertEqual(result.text_message_id, result.document_message_id)
        self.assertEqual(pdf.invoice_payloads[0], payload)

    def test_invoice_uses_configured_text_template(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        result = send_order_invoice(
            gateway,
            FakePdfGateway(),
            FakePhoneGateway("0944123456"),
            "DCO-0001",
            {"kind": "customer_invoice"},
            text_template="فاتورة طلبك {order_name}",
            session_store=_store(),
        )
        self.assertTrue(result.ok)
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents[0][5], "فاتورة طلبك DCO-0001")

    def test_disconnected_session_does_not_send_invoice(self) -> None:
        gateway = FakeWhatsAppGateway([_session(status="disconnected")])
        with self.assertRaises(WhatsAppError) as raised:
            send_order_invoice(
                gateway,
                FakePdfGateway(),
                FakePhoneGateway(),
                "DCO-0001",
                {"kind": "customer_invoice"},
                session_store=_store(),
            )
        self.assertEqual(raised.exception.code, "session_not_ready")
        self.assertEqual(gateway.texts, [])
        self.assertEqual(gateway.documents, [])


class WhatsAppSendStageCompletionTests(unittest.TestCase):
    def test_sends_text_only_with_order_and_stage_placeholders(self) -> None:
        gateway = FakeWhatsAppGateway([_session()])
        result = send_stage_completion(
            gateway,
            FakePhoneGateway("0944123456"),
            "DCO-0001",
            "CNC",
            text_template="طلب {order_name} غادر {stage_label}",
            session_store=_store(),
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.chat_id, "963944123456@c.us")
        self.assertEqual(gateway.texts[0][2], "طلب DCO-0001 غادر CNC")
        self.assertEqual(gateway.documents, [])
        self.assertEqual(
            stage_completion_text("DCO-0001", "CNC"),
            "طلبك رقم DCO-0001 اكتملت مرحلة CNC",
        )

    def test_disconnected_session_does_not_send_stage_text(self) -> None:
        gateway = FakeWhatsAppGateway([_session(status="disconnected")])
        with self.assertRaises(WhatsAppError) as raised:
            send_stage_completion(
                gateway,
                FakePhoneGateway(),
                "DCO-0001",
                "CNC",
                session_store=_store(),
            )
        self.assertEqual(raised.exception.code, "session_not_ready")
        self.assertEqual(gateway.texts, [])

    def test_stage_completion_use_case_stays_frappe_free(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "application"
            / "whatsapp"
            / "send_stage_completion.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertIn("format_whatsapp_preamble", source)


if __name__ == "__main__":
    unittest.main()
