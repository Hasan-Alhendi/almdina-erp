"""OpenWA inbound adapter: signature bytes, mapping, and trusted phone rules."""

from __future__ import annotations

import json
import unittest
from datetime import timezone

from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import InboundMessageKind
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_openwa_inbound import (
    OpenWAInboundError,
    map_openwa_message_received,
    parse_openwa_envelope,
    sign_openwa_body,
    trusted_phone_from_openwa_sender_phone,
    verify_openwa_signature,
)

SECRET = "test-openwa-webhook-secret"
CONNECTION = "customer-bot-openwa"


def _envelope(**overrides) -> dict:
    payload = {
        "event": "message.received",
        "timestamp": 1_700_000_000_000,
        "sessionId": "session-1",
        "idempotencyKey": "idem-1",
        "deliveryId": "delivery-1",
        "data": {
            "id": "msg-1",
            "chatId": "963988100101@c.us",
            "from": "963988100101@c.us",
            "to": "factory@c.us",
            "body": "hello",
            "type": "text",
            "timestamp": 1_700_000_000,
            "fromMe": False,
            "isGroup": False,
            "senderPhone": "963988100101",
        },
    }
    for key, value in overrides.items():
        if key == "data" and isinstance(value, dict):
            payload["data"] = {**payload["data"], **value}
        else:
            payload[key] = value
    return payload


def _body(payload: dict, *, separators: tuple[str, str] = (",", ":")) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=separators).encode("utf-8")


class OpenWAInboundAdapterTests(unittest.TestCase):
    def test_signature_accepts_exact_raw_bytes(self) -> None:
        raw = _body(_envelope())
        header = sign_openwa_body(raw, SECRET)
        self.assertTrue(verify_openwa_signature(raw_body=raw, signature_header=header, secret=SECRET))

    def test_signature_rejects_missing_wrong_and_tampered_body(self) -> None:
        raw = _body(_envelope())
        header = sign_openwa_body(raw, SECRET)
        self.assertFalse(verify_openwa_signature(raw_body=raw, signature_header=None, secret=SECRET))
        self.assertFalse(
            verify_openwa_signature(raw_body=raw, signature_header="sha256=deadbeef", secret=SECRET)
        )
        tampered = raw.replace(b"hello", b"hallo")
        self.assertFalse(
            verify_openwa_signature(raw_body=tampered, signature_header=header, secret=SECRET)
        )

    def test_signature_uses_original_bytes_not_reserialized_json(self) -> None:
        compact = _body(_envelope(), separators=(",", ":"))
        spaced = _body(_envelope(), separators=(", ", ": "))
        self.assertNotEqual(compact, spaced)
        header = sign_openwa_body(compact, SECRET)
        self.assertTrue(verify_openwa_signature(raw_body=compact, signature_header=header, secret=SECRET))
        self.assertFalse(verify_openwa_signature(raw_body=spaced, signature_header=header, secret=SECRET))
        self.assertEqual(parse_openwa_envelope(compact)["idempotencyKey"], "idem-1")
        self.assertEqual(parse_openwa_envelope(spaced)["idempotencyKey"], "idem-1")

    def test_text_message_maps_to_inbound_contract(self) -> None:
        message = map_openwa_message_received(_envelope(), connection_ref=CONNECTION)
        self.assertEqual(message.connection_ref, CONNECTION)
        self.assertEqual(message.provider_event_id, "idem-1")
        self.assertEqual(message.conversation_id, "963988100101@c.us")
        self.assertEqual(message.sender_id, "963988100101@c.us")
        self.assertEqual(message.kind, InboundMessageKind.TEXT)
        self.assertEqual(message.text, "hello")
        self.assertFalse(message.from_own_account)
        self.assertFalse(message.is_group)
        self.assertEqual(message.normalized_phone, "+963988100101")
        self.assertEqual(message.occurred_at.tzinfo, timezone.utc)

    def test_group_uses_author_and_sender_phone_optional(self) -> None:
        message = map_openwa_message_received(
            _envelope(
                data={
                    "isGroup": True,
                    "from": "120363@g.us",
                    "chatId": "120363@g.us",
                    "author": "963988100101@lid",
                    "senderPhone": None,
                }
            ),
            connection_ref=CONNECTION,
        )
        self.assertTrue(message.is_group)
        self.assertEqual(message.sender_id, "963988100101@lid")
        self.assertIsNone(message.normalized_phone)

    def test_delivery_id_is_not_the_event_key(self) -> None:
        first = map_openwa_message_received(
            _envelope(deliveryId="delivery-a"),
            connection_ref=CONNECTION,
        )
        second = map_openwa_message_received(
            _envelope(deliveryId="delivery-b"),
            connection_ref=CONNECTION,
        )
        self.assertEqual(first.provider_event_id, second.provider_event_id)

    def test_missing_or_wrong_types_fail_closed(self) -> None:
        cases = (
            {"idempotencyKey": ""},
            {"data": {"chatId": ""}},
            {"data": {"fromMe": "no"}},
            {"data": {"isGroup": 0}},
            {"data": {"timestamp": "now"}},
            {"data": {"type": 1}},
            {"data": {"body": 9}},
            {"data": {"isGroup": True, "author": ""}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(OpenWAInboundError):
                    map_openwa_message_received(_envelope(**overrides), connection_ref=CONNECTION)

    def test_own_group_status_and_attachments_are_non_operational_shape(self) -> None:
        own = map_openwa_message_received(_envelope(data={"fromMe": True}), connection_ref=CONNECTION)
        group = map_openwa_message_received(
            _envelope(data={"isGroup": True, "author": "a@c.us", "from": "g@g.us", "chatId": "g@g.us"}),
            connection_ref=CONNECTION,
        )
        status = map_openwa_message_received(
            _envelope(data={"isStatusBroadcast": True, "chatId": "status@broadcast", "from": "status@broadcast"}),
            connection_ref=CONNECTION,
        )
        image = map_openwa_message_received(_envelope(data={"type": "image", "body": ""}), connection_ref=CONNECTION)
        self.assertTrue(own.from_own_account)
        self.assertTrue(group.is_group)
        self.assertEqual(status.kind, InboundMessageKind.OTHER)
        self.assertEqual(image.kind, InboundMessageKind.OTHER)
        self.assertEqual(image.text, "")

    def test_trusted_sender_phone_rules(self) -> None:
        self.assertEqual(trusted_phone_from_openwa_sender_phone("963988100101"), "+963988100101")
        self.assertEqual(trusted_phone_from_openwa_sender_phone("+963988100101"), "+963988100101")
        self.assertEqual(trusted_phone_from_openwa_sender_phone("0988100101"), "+963988100101")
        self.assertIsNone(trusted_phone_from_openwa_sender_phone("963988100101@lid"))
        self.assertIsNone(trusted_phone_from_openwa_sender_phone(""))
        self.assertIsNone(trusted_phone_from_openwa_sender_phone(None))
        self.assertIsNone(trusted_phone_from_openwa_sender_phone("12345"))
        # Body / contact are never consulted by the helper; callers must not pass them.
        self.assertIsNone(trusted_phone_from_openwa_sender_phone("not-a-phone"))

    def test_lid_without_sender_phone_leaves_phone_empty(self) -> None:
        message = map_openwa_message_received(
            _envelope(
                data={
                    "from": "1234567890@lid",
                    "chatId": "1234567890@lid",
                    "senderPhone": None,
                    "contact": {"number": "963988100101"},
                }
            ),
            connection_ref=CONNECTION,
        )
        self.assertEqual(message.sender_id, "1234567890@lid")
        self.assertIsNone(message.normalized_phone)


if __name__ == "__main__":
    unittest.main()
