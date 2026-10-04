from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.whatsapp.session_policy import (
    SESSION_NAME_PREFIX,
    SessionNameError,
    is_working,
    needs_qr,
    sessions_named,
    should_create_session,
    unique_session_name,
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

    def test_create_is_refused_when_the_stored_session_still_exists(self) -> None:
        decision = should_create_session("sid-1", remote_exists=True)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "session_already_exists")

    def test_create_is_allowed_when_nothing_is_stored(self) -> None:
        decision = should_create_session("", remote_exists=False)
        self.assertTrue(decision.allowed)

    def test_create_is_allowed_when_the_stored_session_is_gone(self) -> None:
        decision = should_create_session("sid-1", remote_exists=False)
        self.assertTrue(decision.allowed)

    def test_named_lookup_ignores_other_projects(self) -> None:
        matches = sessions_named(
            [
                {"id": "other", "name": "dashboard"},
                {"id": "ours", "name": "almdina-ours"},
            ],
            "almdina-ours",
        )
        self.assertEqual([row["id"] for row in matches], ["ours"])

    def test_named_lookup_returns_every_exact_match(self) -> None:
        matches = sessions_named(
            [
                {"id": "a", "name": "almdina-dup"},
                {"id": "b", "name": "almdina-dup"},
            ],
            "almdina-dup",
        )
        self.assertEqual([row["id"] for row in matches], ["a", "b"])

    def test_unique_name_skips_a_name_that_already_exists(self) -> None:
        draws = iter(["taken", "fresh"])
        name = unique_session_name(["almdina-taken", "dashboard"], lambda: next(draws))
        self.assertEqual(name, f"{SESSION_NAME_PREFIX}fresh")

    def test_unique_name_fails_when_every_draw_collides(self) -> None:
        with self.assertRaises(SessionNameError) as raised:
            unique_session_name(["almdina-same"], lambda: "same")
        self.assertEqual(raised.exception.code, "name_exhausted")

    def test_other_server_sessions_do_not_block_create(self) -> None:
        decision = should_create_session(None, remote_exists=False)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, "allowed")


if __name__ == "__main__":
    unittest.main()
