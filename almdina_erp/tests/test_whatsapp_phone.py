from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.whatsapp.phone import (
    PhoneNormalizationError,
    normalize_syrian_whatsapp_chat_id,
)


class SyrianWhatsAppPhoneTests(unittest.TestCase):
    def test_normalizes_local_leading_zero(self) -> None:
        self.assertEqual(
            normalize_syrian_whatsapp_chat_id("0944 123 456"),
            "963944123456@c.us",
        )

    def test_normalizes_national_number_without_zero(self) -> None:
        self.assertEqual(
            normalize_syrian_whatsapp_chat_id("944123456"),
            "963944123456@c.us",
        )

    def test_normalizes_plus_country_code(self) -> None:
        self.assertEqual(
            normalize_syrian_whatsapp_chat_id("+963944123456"),
            "963944123456@c.us",
        )

    def test_normalizes_international_00_prefix(self) -> None:
        self.assertEqual(
            normalize_syrian_whatsapp_chat_id("00963-944-123-456"),
            "963944123456@c.us",
        )

    def test_missing_phone_is_explicit(self) -> None:
        with self.assertRaises(PhoneNormalizationError) as raised:
            normalize_syrian_whatsapp_chat_id("   ")
        self.assertEqual(raised.exception.code, "missing_phone")

    def test_non_syrian_number_is_rejected(self) -> None:
        with self.assertRaises(PhoneNormalizationError) as raised:
            normalize_syrian_whatsapp_chat_id("0501234567")
        self.assertEqual(raised.exception.code, "invalid_syrian_phone")

    def test_landline_is_rejected(self) -> None:
        with self.assertRaises(PhoneNormalizationError) as raised:
            normalize_syrian_whatsapp_chat_id("0111234567")
        self.assertEqual(raised.exception.code, "invalid_syrian_phone")


if __name__ == "__main__":
    unittest.main()
