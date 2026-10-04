from __future__ import annotations

import re


CHAT_ID_SUFFIX = "@c.us"
SYRIA_COUNTRY_CODE = "963"
_NON_DIGITS = re.compile(r"\D+")


class PhoneNormalizationError(ValueError):
    """Raised when a customer phone number cannot become a Syrian WhatsApp chat id."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _digits_only(value: object) -> str:
    return _NON_DIGITS.sub("", str(value or ""))


def normalize_syrian_whatsapp_chat_id(raw: object) -> str:
    """Return ``9639XXXXXXXX@c.us`` for a Syrian mobile number.

    Accepted shapes include local ``09…`` / ``9…``, ``+963…``, and ``00963…``.
    A leading zero is dropped before the country code is applied.
    """

    digits = _digits_only(raw)
    if not digits:
        raise PhoneNormalizationError(
            "missing_phone",
            "لا يوجد رقم هاتف للزبون على الطلب.",
        )
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    if not digits.startswith(SYRIA_COUNTRY_CODE):
        digits = f"{SYRIA_COUNTRY_CODE}{digits}"
    national = digits[len(SYRIA_COUNTRY_CODE) :]
    if len(digits) != 12 or len(national) != 9 or not national.startswith("9"):
        raise PhoneNormalizationError(
            "invalid_syrian_phone",
            "رقم هاتف الزبون غير صالح. يجب أن يكون رقمًا سوريًا.",
        )
    return f"{digits}{CHAT_ID_SUFFIX}"


__all__ = [
    "CHAT_ID_SUFFIX",
    "PhoneNormalizationError",
    "SYRIA_COUNTRY_CODE",
    "normalize_syrian_whatsapp_chat_id",
]
