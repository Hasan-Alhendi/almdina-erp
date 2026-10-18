"""Contracts for the step-1 customer-bot foundation.

The two reply ports below are different stand-ins. Application code calls
the same injected protocol either way and does not open a connection.
"""

from __future__ import annotations

import ast
import socket
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from almdina_erp.almdina_erp.application.customer_bot import (
    BotReplyPortError,
    BotTextReplyPort,
    dispatch_text_reply,
)
from almdina_erp.almdina_erp.domain.customer_bot import (
    BotGatewayCapabilities,
    InboundMessageKind,
    SendDisposition,
    TextReplyRequest,
    TextSendResult,
    build_inbound_customer_message,
    is_confirmed_rejection,
    is_unknown_send_outcome,
    provider_acceptance_confirms_customer_delivery,
)

ROOT = Path(__file__).resolve().parents[1]
CUSTOMER_BOT_ROOTS = (
    ROOT / "almdina_erp" / "domain" / "customer_bot",
    ROOT / "almdina_erp" / "application" / "customer_bot",
)
_FORBIDDEN_IMPORT_MARKERS = (
    "frappe",
    "infrastructure",
    "services",
    "doctype",
    "presentation",
    "whatsapp",
    "openwa",
    "socket",
    "urllib",
    "http",
    "requests",
    "httpx",
)


def _forbid_network(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("customer-bot tests must not open a network connection")


def _occurred_at() -> datetime:
    return datetime(2026, 10, 18, 8, 30, tzinfo=timezone.utc)


def _reply() -> TextReplyRequest:
    return TextReplyRequest(
        reply_id="reply-42",
        connection_ref="factory-connection-1",
        destination_id="conversation-9",
        text="  حالة الطلب  ",
    )


class _MemoryAcceptingReplyPort:
    """In-memory port that records an accepted send and supports idempotent ids."""

    def __init__(self) -> None:
        self.requests: list[TextReplyRequest] = []
        self._capabilities = BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=True,
        )

    def capabilities(self) -> BotGatewayCapabilities:
        return self._capabilities

    def send_text_reply(self, request: TextReplyRequest) -> TextSendResult:
        self.requests.append(request)
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=SendDisposition.ACCEPTED,
            provider_message_id=f"provider-{request.reply_id}",
            reason_code="provider_accepted",
        )


class _ScriptedReplyPort:
    """Separate port whose outcome and capabilities are chosen by the test."""

    def __init__(
        self,
        disposition: SendDisposition,
        capabilities: BotGatewayCapabilities,
    ) -> None:
        self._disposition = disposition
        self._capabilities = capabilities
        self.calls = 0
        self.last_destination_id = ""

    def capabilities(self) -> BotGatewayCapabilities:
        return self._capabilities

    def send_text_reply(self, request: TextReplyRequest) -> TextSendResult:
        self.calls += 1
        self.last_destination_id = request.destination_id
        provider_message_id = None
        if self._disposition is SendDisposition.ACCEPTED:
            provider_message_id = "provider-scripted"
        reason_code = {
            SendDisposition.ACCEPTED: "provider_accepted",
            SendDisposition.REJECTED: "provider_rejected",
            SendDisposition.UNKNOWN: "timeout_after_possible_accept",
        }[self._disposition]
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id=request.destination_id,
            disposition=self._disposition,
            provider_message_id=provider_message_id,
            reason_code=reason_code,
        )


class _RaisingReplyPort:
    def capabilities(self) -> BotGatewayCapabilities:
        return BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=False,
        )

    def send_text_reply(self, request: TextReplyRequest) -> TextSendResult:
        del request
        raise TimeoutError("simulated provider timeout before a result existed")


class _DestinationRewritingPort:
    def capabilities(self) -> BotGatewayCapabilities:
        return BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=False,
        )

    def send_text_reply(self, request: TextReplyRequest) -> TextSendResult:
        return TextSendResult(
            reply_id=request.reply_id,
            connection_ref=request.connection_ref,
            destination_id="other-destination",
            disposition=SendDisposition.ACCEPTED,
            provider_message_id="provider-rewritten",
            reason_code="provider_accepted",
        )


class TestCustomerBotContracts(unittest.TestCase):
    def setUp(self) -> None:
        for patcher in (
            patch.object(socket, "socket", _forbid_network),
            patch.object(socket, "create_connection", _forbid_network),
            patch.object(urllib.request, "urlopen", _forbid_network),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_two_ports_share_one_application_use_case(self) -> None:
        request = _reply()
        accepting = _MemoryAcceptingReplyPort()
        scripted = _ScriptedReplyPort(
            SendDisposition.ACCEPTED,
            BotGatewayCapabilities(
                sends_text=True,
                supports_interactive_options=True,
                supports_idempotent_send=False,
            ),
        )
        self.assertIsInstance(accepting, BotTextReplyPort)
        self.assertIsInstance(scripted, BotTextReplyPort)
        self.assertEqual(accepting.__class__.__bases__, (object,))
        self.assertEqual(scripted.__class__.__bases__, (object,))
        self.assertIsNot(accepting.__class__, scripted.__class__)

        accepted = dispatch_text_reply(accepting, request)
        also_accepted = dispatch_text_reply(scripted, request)

        self.assertEqual(accepted.disposition, SendDisposition.ACCEPTED)
        self.assertEqual(also_accepted.disposition, SendDisposition.ACCEPTED)
        self.assertEqual(accepted.provider_message_id, "provider-reply-42")
        self.assertEqual(also_accepted.provider_message_id, "provider-scripted")
        self.assertEqual(len(accepting.requests), 1)
        self.assertEqual(scripted.calls, 1)
        self.assertFalse(accepting.capabilities().supports_interactive_options)
        self.assertTrue(scripted.capabilities().supports_interactive_options)
        self.assertTrue(accepting.capabilities().supports_idempotent_send)
        self.assertFalse(scripted.capabilities().supports_idempotent_send)
        self.assertNotIn("_MemoryAcceptingReplyPort", _application_source())
        self.assertNotIn("_ScriptedReplyPort", _application_source())

    def test_reply_ids_and_destination_survive_either_port(self) -> None:
        request = _reply()
        ports = (
            _MemoryAcceptingReplyPort(),
            _ScriptedReplyPort(
                SendDisposition.UNKNOWN,
                BotGatewayCapabilities(
                    sends_text=True,
                    supports_interactive_options=False,
                    supports_idempotent_send=False,
                ),
            ),
        )
        for port in ports:
            result = dispatch_text_reply(port, request)
            self.assertEqual(result.reply_id, "reply-42")
            self.assertEqual(result.connection_ref, "factory-connection-1")
            self.assertEqual(result.destination_id, "conversation-9")
        self.assertEqual(request.text, "حالة الطلب")

    def test_confirmed_rejection_is_distinct_from_an_unknown_outcome(self) -> None:
        capabilities = BotGatewayCapabilities(
            sends_text=True,
            supports_interactive_options=False,
            supports_idempotent_send=False,
        )
        rejected = dispatch_text_reply(
            _ScriptedReplyPort(SendDisposition.REJECTED, capabilities),
            _reply(),
        )
        unknown = dispatch_text_reply(
            _ScriptedReplyPort(SendDisposition.UNKNOWN, capabilities),
            _reply(),
        )
        accepted = dispatch_text_reply(_MemoryAcceptingReplyPort(), _reply())

        self.assertTrue(is_confirmed_rejection(rejected))
        self.assertFalse(is_unknown_send_outcome(rejected))
        self.assertEqual(rejected.reason_code, "provider_rejected")
        self.assertIsNone(rejected.provider_message_id)

        self.assertTrue(is_unknown_send_outcome(unknown))
        self.assertFalse(is_confirmed_rejection(unknown))
        self.assertEqual(unknown.reason_code, "timeout_after_possible_accept")
        self.assertIsNone(unknown.provider_message_id)

        self.assertEqual(accepted.disposition, SendDisposition.ACCEPTED)
        self.assertFalse(provider_acceptance_confirms_customer_delivery(accepted))
        self.assertFalse(provider_acceptance_confirms_customer_delivery(rejected))
        self.assertFalse(provider_acceptance_confirms_customer_delivery(unknown))
        self.assertTrue(
            {rejected.disposition, unknown.disposition, accepted.disposition}
            == set(SendDisposition)
        )

    def test_unknown_outcome_is_not_retried_by_application(self) -> None:
        port = _ScriptedReplyPort(
            SendDisposition.UNKNOWN,
            BotGatewayCapabilities(
                sends_text=True,
                supports_interactive_options=False,
                supports_idempotent_send=True,
            ),
        )
        result = dispatch_text_reply(port, _reply())
        self.assertEqual(port.calls, 1)
        self.assertTrue(is_unknown_send_outcome(result))
        self.assertEqual(port.last_destination_id, "conversation-9")

    def test_unsupported_text_is_a_confirmed_rejection_without_calling_send(self) -> None:
        port = _ScriptedReplyPort(
            SendDisposition.ACCEPTED,
            BotGatewayCapabilities(
                sends_text=False,
                supports_interactive_options=True,
                supports_idempotent_send=True,
            ),
        )
        result = dispatch_text_reply(port, _reply())
        self.assertEqual(port.calls, 0)
        self.assertTrue(is_confirmed_rejection(result))
        self.assertEqual(result.reason_code, "text_send_unsupported")
        self.assertEqual(result.reply_id, "reply-42")
        self.assertEqual(result.destination_id, "conversation-9")
        self.assertFalse(provider_acceptance_confirms_customer_delivery(result))

    def test_a_port_exception_is_not_relabelled_as_unknown(self) -> None:
        with self.assertRaises(TimeoutError):
            dispatch_text_reply(_RaisingReplyPort(), _reply())

    def test_a_port_cannot_replace_the_destination(self) -> None:
        with self.assertRaises(BotReplyPortError):
            dispatch_text_reply(_DestinationRewritingPort(), _reply())

    def test_unresolved_sender_id_does_not_become_a_phone(self) -> None:
        for sender_id in ("963944123456@c.us", "963944123456", "+963944123456"):
            message = build_inbound_customer_message(
                connection_ref="factory-connection-1",
                provider_event_id="event-7",
                conversation_id="conversation-9",
                sender_id=sender_id,
                occurred_at=_occurred_at(),
                kind=InboundMessageKind.TEXT,
                text="وين طلبي",
                from_own_account=False,
                is_group=False,
            )
            self.assertEqual(message.sender_id, sender_id)
            self.assertIsNone(message.normalized_phone)

    def test_whatsapp_looking_value_is_rejected_as_a_trusted_phone(self) -> None:
        with self.assertRaises(ValueError):
            build_inbound_customer_message(
                connection_ref="factory-connection-1",
                provider_event_id="event-7",
                conversation_id="conversation-9",
                sender_id="user-1",
                occurred_at=_occurred_at(),
                kind=InboundMessageKind.TEXT,
                text="مرحبا",
                from_own_account=False,
                is_group=False,
                trusted_normalized_phone="963944123456@c.us",
            )

    def test_explicit_trusted_phone_stays_separate_from_the_sender_id(self) -> None:
        message = build_inbound_customer_message(
            connection_ref=" factory-connection-1 ",
            provider_event_id="event-7",
            conversation_id="conversation-9",
            sender_id="provider-user-1",
            occurred_at=_occurred_at(),
            kind=InboundMessageKind.TEXT,
            text="مرحبا",
            from_own_account=False,
            is_group=False,
            trusted_normalized_phone=" +963944123456 ",
        )
        self.assertEqual(message.connection_ref, "factory-connection-1")
        self.assertEqual(message.provider_event_id, "event-7")
        self.assertEqual(message.normalized_phone, "+963944123456")
        self.assertNotEqual(message.normalized_phone, message.sender_id)
        self.assertEqual(message.occurred_at, _occurred_at())
        self.assertEqual(message.kind, InboundMessageKind.TEXT)
        self.assertEqual(message.text, "مرحبا")

    def test_own_account_and_group_messages_keep_their_flags(self) -> None:
        own_account = _inbound(from_own_account=True, is_group=False)
        group = _inbound(from_own_account=False, is_group=True)
        self.assertTrue(own_account.from_own_account)
        self.assertFalse(own_account.is_group)
        self.assertFalse(group.from_own_account)
        self.assertTrue(group.is_group)

    def test_naive_timestamp_and_missing_flags_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            _inbound(occurred_at=datetime(2026, 10, 18, 8, 30))
        with self.assertRaises(TypeError):
            build_inbound_customer_message(
                connection_ref="factory-connection-1",
                provider_event_id="event-7",
                conversation_id="conversation-9",
                sender_id="provider-user-1",
                occurred_at=_occurred_at(),
                kind=InboundMessageKind.OTHER,
                text="",
            )

    def test_rejected_and_unknown_results_cannot_carry_a_provider_message_id(self) -> None:
        for disposition in (SendDisposition.REJECTED, SendDisposition.UNKNOWN):
            with self.assertRaises(ValueError):
                TextSendResult(
                    reply_id="reply-42",
                    connection_ref="factory-connection-1",
                    destination_id="conversation-9",
                    disposition=disposition,
                    provider_message_id="provider-should-not-stick",
                    reason_code="provider_rejected",
                )

    def test_reply_contract_has_no_secret_or_session_fields(self) -> None:
        self.assertEqual(
            set(TextReplyRequest.__dataclass_fields__),
            {"reply_id", "connection_ref", "destination_id", "text"},
        )
        self.assertEqual(
            set(BotGatewayCapabilities.__dataclass_fields__),
            {"sends_text", "supports_interactive_options", "supports_idempotent_send"},
        )

    def test_domain_and_application_stay_free_of_framework_and_provider_imports(self) -> None:
        offenders: list[str] = []
        for root in CUSTOMER_BOT_ROOTS:
            for path in sorted(root.rglob("*.py")):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(path))
                imported: list[str] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imported.append(node.module or "")
                for target in imported:
                    if any(marker in target.split(".") for marker in _FORBIDDEN_IMPORT_MARKERS):
                        offenders.append(f"{path.relative_to(ROOT)} imports {target}")
                for marker in ("openwa", "api_key", "access_token", "qr_code", "graph.facebook"):
                    if marker in source:
                        offenders.append(f"{path.relative_to(ROOT)} mentions {marker}")
        self.assertEqual(offenders, [])


def _application_source() -> str:
    application = ROOT / "almdina_erp" / "application" / "customer_bot"
    return "\n".join(path.read_text(encoding="utf-8") for path in application.rglob("*.py"))


def _inbound(**overrides: object):
    payload = {
        "connection_ref": "factory-connection-1",
        "provider_event_id": "event-7",
        "conversation_id": "conversation-9",
        "sender_id": "provider-user-1",
        "occurred_at": _occurred_at(),
        "kind": InboundMessageKind.TEXT,
        "text": "مرحبا",
        "from_own_account": False,
        "is_group": False,
    }
    payload.update(overrides)
    return build_inbound_customer_message(**payload)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
