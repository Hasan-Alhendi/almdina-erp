"""Message age policy with an injected clock. No sleep."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from almdina_erp.almdina_erp.application.customer_bot.accept_inbound_message import (
    accept_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_age import (
    AGE_FUTURE,
    AGE_INVALID,
    AGE_OK,
    AGE_STALE,
    DEFAULT_MAX_FUTURE_SKEW,
    DEFAULT_MAX_MESSAGE_AGE,
    classify_message_age,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import DUPLICATE, IGNORED, PROCESSED
from almdina_erp.tests.customer_bot_session_memory import MemoryCustomerBotSessionStore
from almdina_erp.tests.test_customer_bot_inbound_session import (
    NOW,
    _Clock,
    _Directory,
    _Orders,
    _Routes,
    _Services,
    _Settings,
    _Stages,
    _header,
    _message,
)


class MessageAgeUnitTests(unittest.TestCase):
    def test_classify_bounds(self) -> None:
        now = NOW
        self.assertEqual(classify_message_age(now, now=now), AGE_OK)
        self.assertEqual(
            classify_message_age(now - DEFAULT_MAX_MESSAGE_AGE, now=now),
            AGE_OK,
        )
        self.assertEqual(
            classify_message_age(now - DEFAULT_MAX_MESSAGE_AGE - timedelta(seconds=1), now=now),
            AGE_STALE,
        )
        self.assertEqual(
            classify_message_age(now + DEFAULT_MAX_FUTURE_SKEW, now=now),
            AGE_OK,
        )
        self.assertEqual(
            classify_message_age(now + DEFAULT_MAX_FUTURE_SKEW + timedelta(seconds=1), now=now),
            AGE_FUTURE,
        )
        self.assertEqual(classify_message_age(None, now=now), AGE_INVALID)
        naive = datetime(2026, 10, 22, 9, 0)
        self.assertEqual(classify_message_age(naive, now=now), AGE_INVALID)


class MessageAgeAcceptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        self.settings = _Settings()
        self.directory = _Directory()
        self.sessions = MemoryCustomerBotSessionStore()

    def accept(self, message, **kwargs):
        return accept_inbound_customer_message(
            message,
            sessions=self.sessions,
            settings=self.settings,
            directory=self.directory,
            headers=_Orders((_header("DCO-A"),)),
            stages=_Stages(),
            routes=_Routes(),
            services=_Services(),
            now=self.clock.now,
            **kwargs,
        )

    def test_stale_message_is_terminal_ignored_without_replies(self) -> None:
        stale = _message(
            "hello",
            "age-stale",
            occurred_at=NOW - timedelta(minutes=31),
        )
        first = self.accept(stale)
        self.assertEqual(first.disposition, IGNORED)
        self.assertEqual(len(self.sessions.replies), 0)
        # A later bot enablement must not re-run the stored event.
        self.settings.enabled = False
        self.settings.enabled = True
        again = self.accept(stale)
        self.assertEqual(again.disposition, DUPLICATE)
        self.assertEqual(len(self.sessions.replies), 0)

    def test_delivery_time_is_not_used_for_age(self) -> None:
        # occurred_at is old; advancing the clock (as if a late webhook arrived)
        # still classifies from occurred_at, not from a new delivery attempt clock
        # alone when the message itself is already beyond max age at accept time.
        old = _message("hello", "age-late-delivery", occurred_at=NOW - timedelta(minutes=5))
        self.clock.now = NOW + timedelta(minutes=40)
        outcome = self.accept(old)
        self.assertEqual(outcome.disposition, IGNORED)

    def test_fresh_message_still_processes(self) -> None:
        outcome = self.accept(_message("hello", "age-ok", occurred_at=NOW - timedelta(minutes=1)))
        self.assertEqual(outcome.disposition, PROCESSED)
        self.assertGreaterEqual(len(self.sessions.replies), 1)

    def test_duplicate_recorded_event_not_rerun_by_age_policy(self) -> None:
        message = _message("hello", "age-dup", occurred_at=NOW)
        self.assertEqual(self.accept(message).disposition, PROCESSED)
        count = len(self.sessions.replies)
        # Even if we inject a future clock, the event key already completed.
        self.clock.now = NOW + timedelta(hours=2)
        self.assertEqual(self.accept(message).disposition, DUPLICATE)
        self.assertEqual(len(self.sessions.replies), count)


if __name__ == "__main__":
    unittest.main()
