"""Immediate reply-delivery enqueue contracts (no live WhatsApp)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    InboundAcceptance,
)
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import PROCESSED
from almdina_erp.almdina_erp.infrastructure.frappe import customer_bot_inbound_gateway as gw
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery import (
    LIVE_REPLY_DELIVERY_ENABLED,
    _DELIVERY_JOB_METHOD,
    _delivery_job_id,
    enqueue_customer_bot_reply_delivery,
    run_customer_bot_reply_delivery_job,
    scheduled_customer_bot_reply_tick,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.customer_bot_ops_config import (
    OPS_MODE_PRODUCTION,
    CustomerBotOpsConfig,
)

NOW_UTC = datetime(2026, 10, 22, 13, 30, tzinfo=timezone.utc)


def _patch_frappe_module(fake_frappe: MagicMock):
    """``enqueue_customer_bot_reply_delivery`` imports frappe inside the body."""

    return patch.dict("sys.modules", {"frappe": fake_frappe})


class ReplyDeliveryEnqueueTests(unittest.TestCase):
    def test_enqueue_registers_after_commit_with_dedupe_job_id(self) -> None:
        fake_frappe = MagicMock()
        hooks: list = []
        fake_frappe.db.after_commit = hooks

        def _enqueue(method, **kwargs):
            # Mirror Frappe: defer until commit when enqueue_after_commit is set.
            if kwargs.get("enqueue_after_commit"):
                hooks.append({"method": method, **kwargs})
                return None
            raise AssertionError("expected enqueue_after_commit")

        fake_frappe.enqueue.side_effect = _enqueue

        with _patch_frappe_module(fake_frappe):
            ok = enqueue_customer_bot_reply_delivery(
                connection_ref="conn-a",
                provider_event_id="event-long-enough",
            )

        self.assertTrue(ok)
        fake_frappe.enqueue.assert_called_once()
        kwargs = fake_frappe.enqueue.call_args.kwargs
        self.assertEqual(fake_frappe.enqueue.call_args.args[0], _DELIVERY_JOB_METHOD)
        self.assertTrue(kwargs["enqueue_after_commit"])
        self.assertTrue(kwargs["deduplicate"])
        self.assertEqual(kwargs["job_id"], _delivery_job_id("conn-a", "event-long-enough"))
        self.assertEqual(len(hooks), 1)
        self.assertFalse(LIVE_REPLY_DELIVERY_ENABLED)

    def test_enqueue_not_executed_when_only_rolled_back(self) -> None:
        """Hooks registered with enqueue_after_commit must not run on rollback."""

        fake_frappe = MagicMock()
        after_commit: list = []
        after_rollback: list = []
        fake_frappe.db.after_commit = after_commit
        fake_frappe.db.after_rollback = after_rollback

        def _enqueue(method, **kwargs):
            if kwargs.get("enqueue_after_commit"):
                # Store the deferred call like Frappe's after_commit.add(enqueue_call)
                after_commit.append(lambda: after_commit.append("ran"))
                return None
            raise AssertionError("unexpected immediate enqueue")

        fake_frappe.enqueue.side_effect = _enqueue

        with _patch_frappe_module(fake_frappe):
            self.assertTrue(
                enqueue_customer_bot_reply_delivery(
                    connection_ref="conn-a",
                    provider_event_id="event-rb",
                )
            )
        # Simulate rollback: clear after_commit without running hooks (Frappe clears them).
        deferred = list(after_commit)
        after_commit.clear()
        self.assertEqual(len(deferred), 1)
        self.assertNotIn("ran", after_commit)
        # Immediate queue path was never used.
        self.assertEqual(fake_frappe.enqueue.call_count, 1)
        self.assertTrue(fake_frappe.enqueue.call_args.kwargs["enqueue_after_commit"])

    def test_enqueue_failure_returns_false_without_raising(self) -> None:
        fake_frappe = MagicMock()
        fake_frappe.enqueue.side_effect = RuntimeError("redis down")

        with _patch_frappe_module(fake_frappe):
            ok = enqueue_customer_bot_reply_delivery(
                connection_ref="conn-a",
                provider_event_id="event-1",
            )
        self.assertFalse(ok)
        fake_frappe.log_error.assert_called()

    def test_enqueue_rejects_blank_keys(self) -> None:
        fake_frappe = MagicMock()
        with _patch_frappe_module(fake_frappe):
            self.assertFalse(
                enqueue_customer_bot_reply_delivery(connection_ref="", provider_event_id="e")
            )
            self.assertFalse(
                enqueue_customer_bot_reply_delivery(connection_ref="c", provider_event_id=" ")
            )
        fake_frappe.enqueue.assert_not_called()

    def test_job_ids_differ_for_events_that_share_a_prefix(self) -> None:
        shared = "msg_session_false_120363@g.us_" + ("A" * 80)
        left = shared + "_one"
        right = shared + "_two"
        self.assertNotEqual(_delivery_job_id("conn", left), _delivery_job_id("conn", right))
        self.assertEqual(_delivery_job_id("conn", left), _delivery_job_id("conn", left))

    def test_scheduled_tick_reuses_job_entry(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery.run_customer_bot_reply_delivery_job",
            return_value={"abandoned": 1, "sent": 2},
        ) as job:
            self.assertEqual(scheduled_customer_bot_reply_tick(), {"abandoned": 1, "sent": 2})
        job.assert_called_once_with()

    def test_delivery_job_recovers_then_delivers(self) -> None:
        with patch(
            "almdina_erp.almdina_erp.application.customer_bot.deliver_reply_intents.recover_abandoned_reply_claims",
            return_value=3,
        ) as recover:
            with patch(
                "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_delivery.deliver_customer_bot_replies",
                return_value=1,
            ) as deliver:
                with patch(
                    "almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_reply_repository.FrappeCustomerBotReplyRepository",
                ):
                    result = run_customer_bot_reply_delivery_job()
        self.assertEqual(result, {"abandoned": 3, "sent": 1})
        recover.assert_called_once()
        deliver.assert_called_once_with()


class GatewayEnqueueWiringTests(unittest.TestCase):
    def test_gateway_enqueues_after_processed_even_when_enqueue_returns_false(self) -> None:
        message = build_inbound_customer_message(
            connection_ref="conn-a",
            provider_event_id="event-wire-1",
            conversation_id="chat-a",
            sender_id="sender-a",
            occurred_at=NOW_UTC,
            kind=InboundMessageKind.TEXT,
            text="hi",
            from_own_account=False,
            is_group=False,
            trusted_normalized_phone="+963931644327",
        )

        def fake_accept(_msg, **kwargs):
            cb = kwargs.get("on_replies_committed")
            self.assertIsNotNone(cb)
            assert cb is not None
            cb(2)
            return InboundAcceptance(PROCESSED, messages=(), documents=(), published={})

        with patch.object(
            gw,
            "load_customer_bot_ops",
            return_value=CustomerBotOpsConfig(
                mode=OPS_MODE_PRODUCTION,
                pilot_phone_e164=None,
                started_at=NOW_UTC,
                transport_armed=False,
                transport_live=False,
            ),
        ):
            with patch.object(gw, "accept_inbound_customer_message", side_effect=fake_accept):
                with patch.object(gw, "FrappeCustomerBotSessionRepository"):
                    with patch.object(gw, "FrappeCustomerBotSettingsRepository"):
                        with patch.object(gw, "FrappeCustomerPhoneDirectory"):
                            with patch.object(gw, "FrappeCustomerOrderReader"):
                                with patch.object(gw, "build_customer_bot_services"):
                                    with patch.object(
                                        gw,
                                        "enqueue_customer_bot_reply_delivery",
                                        return_value=False,
                                    ) as enq:
                                        outcome = gw.accept_verified_customer_bot_inbound(message)
        self.assertEqual(outcome.disposition, PROCESSED)
        enq.assert_called_once_with(
            connection_ref="conn-a",
            provider_event_id="event-wire-1",
        )


if __name__ == "__main__":
    unittest.main()
