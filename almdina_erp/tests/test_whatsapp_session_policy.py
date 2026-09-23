from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.whatsapp.session_policy import (
    FACTORY_SESSION_NAME,
    is_working,
    needs_qr,
    select_factory_session,
    should_create_session,
)


class WhatsAppSessionPolicyTests(unittest.TestCase):
    def test_ready_is_the_only_working_status(self) -> None:
        self.assertTrue(is_working("ready"))
        self.assertFalse(is_working("qr_ready"))
        self.assertFalse(is_working("disconnected"))
        self.assertFalse(is_working(""))

    def test_qr_window_statuses(self) -> None:
        self.assertTrue(needs_qr("qr_ready"))
        self.assertTrue(needs_qr("initializing"))
        self.assertFalse(needs_qr("ready"))
        self.assertFalse(needs_qr("failed"))

    def test_create_is_refused_when_any_session_exists(self) -> None:
        decision = should_create_session(
            [{"id": "1", "name": "dashboard-bot", "status": "ready"}]
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "session_already_exists")

    def test_create_is_allowed_when_none_exist(self) -> None:
        decision = should_create_session([])
        self.assertTrue(decision.allowed)

    def test_select_prefers_factory_session_name(self) -> None:
        selected = select_factory_session(
            [
                {"id": "other", "name": "dashboard"},
                {"id": "ours", "name": FACTORY_SESSION_NAME},
            ]
        )
        self.assertEqual(selected["id"], "ours")

    def test_select_binds_to_the_only_dashboard_session(self) -> None:
        selected = select_factory_session([{"id": "dash", "name": "from-dashboard"}])
        self.assertEqual(selected["id"], "dash")

    def test_select_returns_none_when_empty(self) -> None:
        self.assertIsNone(select_factory_session([]))


if __name__ == "__main__":
    unittest.main()
