"""HTTP and MariaDB proof for the authenticated OpenWA inbound webhook.

Uses synthetic bodies and a test HMAC secret. Does not contact WhatsApp, create
a live webhook, or enable reply delivery.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from unittest.mock import patch

import frappe
from frappe.auth import CookieManager, LoginManager
from frappe.tests.test_api import make_request
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_test_client, set_request
from frappe.utils.password import set_encrypted_password

from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    DUPLICATE,
    IGNORED,
    PROCESSED,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_inbound_connection import (
    DOCTYPE,
    load_openwa_inbound_connection,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    LIVE_REPLY_DELIVERY_ENABLED,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import SERVICE_FLAG
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
    FrappeCustomerBotSettingsRepository,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_inbound import (
    sign_openwa_body,
)
from almdina_erp.almdina_erp.services.customer_bot_inbound_service import (
    receive_openwa_customer_bot_event,
)

_ThreadConnectLock = threading.Lock()


class _FakeRequest:
    def __init__(self, body: bytes, signature: str | None) -> None:
        self._body = body
        headers = {"Content-Type": "application/json"}
        if signature:
            headers["X-OpenWA-Signature"] = signature
        self.headers = headers

    def get_data(self, cache: bool = True):
        return self._body


def _invoke_with_request(body: bytes, signature: str | None) -> dict:
    frappe.local.request = _FakeRequest(body, signature)
    if not hasattr(frappe.local, "response") or frappe.local.response is None:
        frappe.local.response = frappe._dict({"http_status_code": 200})
    return receive_openwa_customer_bot_event()

METHOD = (
    "almdina_erp.almdina_erp.services.customer_bot_inbound_service"
    ".receive_openwa_customer_bot_event"
)
INGEST_ROLE = "Almdina Customer Bot Inbound Tester"
SETTINGS_ROLE = "Almdina Customer Bot Settings Tester"
INGEST_USER = "cbot-inbound-tester@example.com"
SETTINGS_USER = "cbot-inbound-settings@example.com"
PREFIX = "cbot-inb-"
SECRET = "unit-test-openwa-webhook-secret"
CONNECTION = PREFIX + "conn"
SESSION = PREFIX + "session"


class TestCustomerBotOpenWAInboundIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls._delete_fixtures()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        cls._delete_fixtures()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self._ensure_role(INGEST_ROLE)
        self._ensure_role(SETTINGS_ROLE)
        self._ensure_user(INGEST_USER, INGEST_ROLE)
        self._ensure_user(SETTINGS_USER, SETTINGS_ROLE)
        self._grant(INGEST_ROLE, DOCTYPE, {"ingest_customer_bot_inbound": 1})
        self._grant(SETTINGS_ROLE, DOCTYPE, {"manage_customer_bot_settings": 1})
        frappe.db.commit()
        frappe.clear_cache()
        self._connection_before = _connection_snapshot()
        self._enabled_before = _bot_enabled()
        self._cleanup_bot_rows()
        self._configure_connection(CONNECTION, SESSION, SECRET)
        self._ensure_bot_enabled()
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup_bot_rows()
        self._restore_connection(self._connection_before)
        self._restore_bot_enabled(self._enabled_before)
        frappe.db.rollback()
        super().tearDown()

    def test_guest_and_unauthorized_user_are_rejected(self) -> None:
        guest = self._post_session_json(user=None)
        self.assertIn(guest.status_code, {401, 403}, guest.get_data(as_text=True))
        denied = self._post_session_json(user=SETTINGS_USER)
        self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))
        self.assertEqual(denied.json["exc_type"], "PermissionError")

    def test_signature_session_and_config_gates(self) -> None:
        body, signature = _signed_body()
        missing = self._invoke(INGEST_USER, body, None)
        self.assertEqual(frappe.local.response.get("http_status_code"), 403)
        self.assertEqual(missing["code"], "invalid_signature")

        wrong = self._invoke(INGEST_USER, body, "sha256=" + ("0" * 64))
        self.assertEqual(frappe.local.response.get("http_status_code"), 403)
        self.assertEqual(wrong["code"], "invalid_signature")

        spaced = json.dumps(json.loads(body), separators=(", ", ": ")).encode("utf-8")
        self.assertNotEqual(body, spaced)
        retimed = self._invoke(INGEST_USER, spaced, signature)
        self.assertEqual(frappe.local.response.get("http_status_code"), 403)
        self.assertEqual(retimed["code"], "invalid_signature")

        mismatched = _signed_body(session_id="other-session")
        bad_session = self._invoke(INGEST_USER, mismatched[0], mismatched[1])
        self.assertEqual(frappe.local.response.get("http_status_code"), 403)
        self.assertEqual(bad_session["code"], "session_mismatch")

        self._configure_connection("", SESSION, SECRET)
        unconfigured = self._invoke(INGEST_USER, body, signature)
        self.assertEqual(frappe.local.response.get("http_status_code"), 503)
        self.assertEqual(unconfigured["code"], "connection_not_configured")

    def test_invalid_payload_after_valid_signature(self) -> None:
        payload = _payload()
        payload["data"]["fromMe"] = "no"
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = sign_openwa_body(body, SECRET)
        response = self._invoke(INGEST_USER, body, signature)
        self.assertEqual(frappe.local.response.get("http_status_code"), 400)
        self.assertFalse(response["ok"])

    def test_exclusions_and_duplicate_delivery_id_change(self) -> None:
        own = _signed_body(idempotency_key=PREFIX + "own", data={"fromMe": True})
        self.assertEqual(self._invoke(INGEST_USER, own[0], own[1])["disposition"], IGNORED)

        group = _signed_body(
            idempotency_key=PREFIX + "group",
            data={"isGroup": True, "from": "g@g.us", "chatId": "g@g.us", "author": "a@c.us"},
        )
        self.assertEqual(self._invoke(INGEST_USER, group[0], group[1])["disposition"], IGNORED)

        status = _signed_body(
            idempotency_key=PREFIX + "status",
            data={"isStatusBroadcast": True, "chatId": "status@broadcast", "from": "status@broadcast"},
        )
        self.assertEqual(self._invoke(INGEST_USER, status[0], status[1])["disposition"], IGNORED)

        image = _signed_body(idempotency_key=PREFIX + "image", data={"type": "image", "body": ""})
        self.assertEqual(self._invoke(INGEST_USER, image[0], image[1])["disposition"], IGNORED)

        first = _signed_body(idempotency_key=PREFIX + "dup", delivery_id="d1")
        second = _signed_body(idempotency_key=PREFIX + "dup", delivery_id="d2")
        accepted = self._invoke(INGEST_USER, first[0], first[1])
        self.assertEqual(frappe.local.response.get("http_status_code"), 200)
        self.assertEqual(accepted["disposition"], PROCESSED)
        replay = self._invoke(INGEST_USER, second[0], second[1])
        self.assertEqual(replay["disposition"], DUPLICATE)
        self.assertEqual(_event_count(PREFIX + "dup"), 1)
        self.assertGreaterEqual(_reply_count(PREFIX + "dup"), 1)

    def test_lid_without_trusted_phone_and_valid_phone(self) -> None:
        lid = _signed_body(
            idempotency_key=PREFIX + "lid",
            data={
                "from": "999@lid",
                "chatId": "999@lid",
                "senderPhone": None,
                "contact": {"number": "963988100101"},
            },
        )
        lid_response = self._invoke(INGEST_USER, lid[0], lid[1])
        self.assertEqual(lid_response["disposition"], PROCESSED)

        phone = _signed_body(
            idempotency_key=PREFIX + "phone",
            data={
                "senderPhone": "963988100202",
                "from": "963988100202@c.us",
                "chatId": "963988100202@c.us",
            },
        )
        phone_response = self._invoke(INGEST_USER, phone[0], phone[1])
        self.assertEqual(phone_response["disposition"], PROCESSED)

    def test_valid_text_persists_intents_without_send_client(self) -> None:
        body, signature = _signed_body(idempotency_key=PREFIX + "ok")
        with patch(
            "almdina_erp.almdina_erp.infrastructure.whatsapp.openwa_client.OpenWAClient"
        ) as client_cls:
            response = self._invoke(INGEST_USER, body, signature)
        self.assertEqual(response["disposition"], PROCESSED)
        self.assertGreaterEqual(_reply_count(PREFIX + "ok"), 1)
        client_cls.assert_not_called()
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)

    def test_transient_failure_returns_retryable_status(self) -> None:
        body, signature = _signed_body(idempotency_key=PREFIX + "fail")
        with patch(
            "almdina_erp.almdina_erp.services.customer_bot_inbound_service.accept_verified_customer_bot_inbound",
            side_effect=RuntimeError("Deadlock found when trying to get lock"),
        ):
            response = self._invoke(INGEST_USER, body, signature)
        self.assertEqual(frappe.local.response.get("http_status_code"), 503)
        self.assertEqual(response["code"], "transient_persistence_error")
        self.assertEqual(_event_count(PREFIX + "fail"), 0)

    def test_concurrent_same_idempotency_key(self) -> None:
        body, signature = _signed_body(idempotency_key=PREFIX + "race", delivery_id="race-a")
        other_body, other_signature = _signed_body(idempotency_key=PREFIX + "race", delivery_id="race-b")
        site = frappe.local.site
        sites_path = frappe.local.sites_path
        results: list[dict] = []
        barrier = threading.Barrier(2)
        lock = threading.Lock()

        def worker(raw: bytes, header: str) -> None:
            with _ThreadConnectLock:
                frappe.init(site=site, sites_path=sites_path)
                frappe.connect()
            try:
                frappe.set_user(INGEST_USER)
                barrier.wait(timeout=10)
                outcome = _invoke_with_request(raw, header)
                with lock:
                    results.append(outcome)
            finally:
                frappe.destroy()

        left = threading.Thread(target=worker, args=(body, signature))
        right = threading.Thread(target=worker, args=(other_body, other_signature))
        left.start()
        right.start()
        left.join()
        right.join()
        self.assertEqual(len(results), 2)
        frappe.db.commit()
        self.assertEqual(_event_count(PREFIX + "race"), 1)
        ok = [item for item in results if item.get("ok")]
        dispositions = {item.get("disposition") or item.get("code") for item in results}
        self.assertTrue(dispositions & {PROCESSED, DUPLICATE, "in_progress", "conversation_busy"})
        self.assertTrue(PROCESSED in dispositions or DUPLICATE in dispositions or "in_progress" in dispositions)

    def test_endpoint_has_no_allow_guest(self) -> None:
        self.assertFalse(getattr(receive_openwa_customer_bot_event, "allow_guest", False))

    def test_http_token_auth_signed_raw_body_round_trip(self) -> None:
        """Full HTTP path: token Authorization + raw-body HMAC, no FakeRequest."""

        api_key, api_secret = self._issue_api_token(INGEST_USER)
        body, signature = _signed_body(idempotency_key=PREFIX + "http-ok")
        ok = self._post_token_raw(api_key, api_secret, body, signature)
        self.assertEqual(ok.status_code, 200, ok.get_data(as_text=True))
        payload = ok.json.get("message") or ok.json
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(payload.get("disposition"), PROCESSED)
        frappe.db.commit()
        self.assertGreaterEqual(_reply_count(PREFIX + "http-ok"), 1)
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)

        # Flip one JSON digit after signing so the HMAC fails while the body can
        # still be parsed. A broken JSON body may be rejected by the framework
        # with 417 before our handler; both paths must leave zero bot rows.
        tampered = body.replace(b'"hello"', b'"hallo"', 1)
        self.assertNotEqual(tampered, body)
        bad_byte = self._post_token_raw(api_key, api_secret, tampered, signature)
        self.assertIn(bad_byte.status_code, {403, 417}, bad_byte.get_data(as_text=True))
        frappe.db.commit()
        self.assertEqual(_event_count(PREFIX + "http-ok"), 1)
        self.assertEqual(_reply_count(PREFIX + "http-tamper"), 0)

        wrong_sig = self._post_token_raw(
            api_key, api_secret, body, "sha256=" + ("a" * 64)
        )
        self.assertEqual(wrong_sig.status_code, 403)

        wrong_session_body, wrong_session_sig = _signed_body(
            idempotency_key=PREFIX + "http-sess", session_id="wrong-session"
        )
        bad_session = self._post_token_raw(
            api_key, api_secret, wrong_session_body, wrong_session_sig
        )
        self.assertEqual(bad_session.status_code, 403)
        frappe.db.commit()
        self.assertEqual(_event_count(PREFIX + "http-sess"), 0)

        first = _signed_body(idempotency_key=PREFIX + "http-dup", delivery_id="d-http-1")
        second = _signed_body(idempotency_key=PREFIX + "http-dup", delivery_id="d-http-2")
        accepted = self._post_token_raw(api_key, api_secret, first[0], first[1])
        self.assertEqual(accepted.status_code, 200, accepted.get_data(as_text=True))
        accepted_payload = accepted.json.get("message") or accepted.json
        self.assertEqual(accepted_payload.get("disposition"), PROCESSED, accepted_payload)
        frappe.db.commit()
        replies_before = _reply_count(PREFIX + "http-dup")
        self.assertGreaterEqual(replies_before, 1)
        replay = self._post_token_raw(api_key, api_secret, second[0], second[1])
        self.assertEqual(replay.status_code, 200, replay.get_data(as_text=True))
        replay_payload = replay.json.get("message") or replay.json
        self.assertEqual(replay_payload.get("disposition"), DUPLICATE)
        frappe.db.commit()
        self.assertEqual(_event_count(PREFIX + "http-dup"), 1)
        self.assertEqual(_reply_count(PREFIX + "http-dup"), replies_before)

        guest = self._post_token_raw("not-a-key", "not-a-secret", body, signature)
        self.assertIn(guest.status_code, {401, 403})

    def test_connection_loader_requires_all_values(self) -> None:
        self._configure_connection(CONNECTION, SESSION, "")
        self.assertIsNone(load_openwa_inbound_connection())
        self._configure_connection(CONNECTION, SESSION, SECRET)
        loaded = load_openwa_inbound_connection()
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.connection_ref, CONNECTION)
        self.assertEqual(loaded.session_id, SESSION)
        self.assertEqual(loaded.webhook_secret, SECRET)

    def _invoke(self, user: str, body: bytes, signature: str | None) -> dict:
        frappe.set_user(user)
        frappe.local.response = frappe._dict({"http_status_code": 200})
        return _invoke_with_request(body, signature)

    def _issue_api_token(self, user: str) -> tuple[str, str]:
        """Create an in-DB API token for the test user. Secrets stay in memory only."""

        frappe.set_user("Administrator")
        user_doc = frappe.get_doc("User", user)
        api_secret = frappe.generate_hash(length=15)
        if not user_doc.api_key:
            user_doc.api_key = frappe.generate_hash(length=15)
        user_doc.api_secret = api_secret
        user_doc.save(ignore_permissions=True)
        frappe.db.commit()
        return str(user_doc.api_key), str(api_secret)

    def _post_token_raw(
        self,
        api_key: str,
        api_secret: str,
        body: bytes,
        signature: str | None,
    ):
        """POST the exact signed bytes with ``Authorization: token …`` like OpenWA."""

        headers = {
            "Authorization": f"token {api_key}:{api_secret}",
            "Content-Type": "application/json",
        }
        if signature:
            headers["X-OpenWA-Signature"] = signature
        return make_request(
            target=get_test_client().post,
            args=(f"/api/method/{METHOD}",),
            kwargs={
                "data": body,
                "headers": headers,
                "base_url": "http://almdina.local",
            },
        )

    def _post_session_json(self, *, user: str | None):
        """HTTP permission probe. Session auth uses Frappe's JSON ``sid`` form."""

        set_request(path="/")
        frappe.local.cookie_manager = CookieManager()
        frappe.local.login_manager = LoginManager()
        if user:
            frappe.local.login_manager.login_as(user)
            payload = {"sid": frappe.session.sid}
        else:
            frappe.set_user("Guest")
            payload = {}
        return make_request(
            target=get_test_client().post,
            args=(f"/api/method/{METHOD}",),
            kwargs={"json": payload, "base_url": "http://almdina.local"},
        )

    def _configure_connection(self, connection_ref: str, session_id: str, secret: str) -> None:
        previous = getattr(frappe.flags, SERVICE_FLAG, False)
        setattr(frappe.flags, SERVICE_FLAG, True)
        try:
            frappe.db.set_single_value(DOCTYPE, "openwa_connection_ref", connection_ref)
            frappe.db.set_single_value(DOCTYPE, "openwa_session_id", session_id)
            if secret:
                set_encrypted_password(DOCTYPE, DOCTYPE, secret, fieldname="openwa_webhook_secret")
            else:
                frappe.db.sql(
                    "delete from `__Auth` where doctype=%s and name=%s and fieldname=%s",
                    (DOCTYPE, DOCTYPE, "openwa_webhook_secret"),
                )
            frappe.clear_cache()
            frappe.db.commit()
        finally:
            setattr(frappe.flags, SERVICE_FLAG, previous)

    def _restore_connection(self, snapshot: dict[str, str]) -> None:
        self._configure_connection(
            snapshot.get("openwa_connection_ref", ""),
            snapshot.get("openwa_session_id", ""),
            snapshot.get("openwa_webhook_secret", ""),
        )

    def _ensure_bot_enabled(self) -> None:
        repository = FrappeCustomerBotSettingsRepository()
        snapshot = repository.load()
        if snapshot.enabled:
            return
        enabled = repository.set_enabled(True, snapshot.revision, "Administrator", frappe.utils.now())
        self.assertIsNotNone(enabled)
        frappe.db.commit()

    def _restore_bot_enabled(self, enabled: bool) -> None:
        repository = FrappeCustomerBotSettingsRepository()
        snapshot = repository.load()
        if bool(snapshot.enabled) == bool(enabled):
            return
        restored = repository.set_enabled(enabled, snapshot.revision, "Administrator", frappe.utils.now())
        self.assertIsNotNone(restored)
        frappe.db.commit()

    def _cleanup_bot_rows(self) -> None:
        # Commit first so deletes see rows written by HTTP worker threads and so
        # we never roll back capability grants from setUp.
        frappe.db.commit()
        for attempt in range(3):
            try:
                frappe.db.sql(
                    "delete from `tabCustomer Bot Reply Intent` where connection_ref like %s",
                    (PREFIX + "%",),
                )
                frappe.db.sql(
                    "delete from `tabCustomer Bot Conversation` where connection_ref like %s",
                    (PREFIX + "%",),
                )
                frappe.db.sql(
                    "delete from `tabCustomer Bot Inbound Event` where connection_ref like %s",
                    (PREFIX + "%",),
                )
                frappe.db.commit()
                return
            except Exception:
                frappe.db.rollback()
                if attempt == 2:
                    raise

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True
            )

    @classmethod
    def _ensure_user(cls, email: str, role: str) -> None:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": role,
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            ).insert(ignore_permissions=True)
        if role not in {row.role for row in (user.roles or [])}:
            user.append("roles", {"role": role})
            user.save(ignore_permissions=True)

    @classmethod
    def _grant(cls, role: str, doctype: str, values: dict[str, int]) -> None:
        frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0})
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
                **values,
            }
        ).insert(ignore_permissions=True)

    @classmethod
    def _delete_fixtures(cls) -> None:
        for email in (INGEST_USER, SETTINGS_USER):
            if frappe.db.exists("User", email):
                frappe.delete_doc("User", email, force=True, ignore_permissions=True)
        for role in (INGEST_ROLE, SETTINGS_ROLE):
            frappe.db.delete("Custom DocPerm", {"role": role})
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()


def _payload(
    *,
    session_id: str = SESSION,
    idempotency_key: str = PREFIX + "event",
    delivery_id: str = "delivery-1",
    data: dict | None = None,
) -> dict:
    base_data = {
        "id": "msg-1",
        "chatId": "963988100101@c.us",
        "from": "963988100101@c.us",
        "to": "factory@c.us",
        "body": "hello",
        "type": "text",
        # Provider message time (not webhook attempt time). Keep it fresh so the
        # age gate accepts the fixture without sleeping.
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "fromMe": False,
        "isGroup": False,
        "senderPhone": "963988100101",
    }
    if data:
        base_data.update(data)
    return {
        "event": "message.received",
        "timestamp": 1_700_000_000_000,
        "sessionId": session_id,
        "idempotencyKey": idempotency_key,
        "deliveryId": delivery_id,
        "data": base_data,
    }


def _signed_body(**kwargs):
    body = json.dumps(_payload(**kwargs), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return body, sign_openwa_body(body, SECRET)


def _connection_snapshot() -> dict[str, str]:
    rows = frappe.db.sql(
        "select field, value from `tabSingles` where doctype=%s and field in %s",
        (DOCTYPE, ("openwa_connection_ref", "openwa_session_id")),
        as_dict=True,
    )
    values = {row.field: str(row.value or "") for row in rows or ()}
    secret = ""
    try:
        secret = str(
            frappe.get_single(DOCTYPE).get_password("openwa_webhook_secret", raise_exception=False) or ""
        )
    except Exception:
        secret = ""
    values["openwa_webhook_secret"] = secret
    return values


def _bot_enabled() -> bool:
    return FrappeCustomerBotSettingsRepository().load().enabled


def _event_count(event_id: str) -> int:
    return int(
        frappe.db.sql(
            """select count(*) from `tabCustomer Bot Inbound Event`
               where connection_ref=%s and provider_event_id=%s""",
            (CONNECTION, event_id),
        )[0][0]
    )


def _reply_count(event_id: str) -> int:
    return int(
        frappe.db.sql(
            """select count(*) from `tabCustomer Bot Reply Intent`
               where connection_ref=%s and provider_event_id=%s""",
            (CONNECTION, event_id),
        )[0][0]
    )
