"""Normalize a customer phone for the customer bot.

The internal shape is E.164. Syrian local forms are accepted. An explicit
international number is validated as itself and is not rewritten as Syrian.
Provider participant ids are not phone input.
"""

from __future__ import annotations

import re


_SEPARATORS = re.compile(r"[\s\u00a0\-\u2010-\u2015.()/,،]+")
_E164_DIGITS = re.compile(r"^[1-9]\d{7,14}$")
_SYRIA_COUNTRY = "963"
_SYRIA_NATIONAL_LENGTH = 9


class CustomerPhoneError(ValueError):
    """A value cannot be used as a customer phone."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def normalize_customer_phone(raw: object) -> str:
    """Return ``+E.164`` or raise ``CustomerPhoneError``.

    ``provider_identifier`` means the value looks like a gateway id, such as
    ``@c.us`` or ``@lid``. ``invalid_phone`` means it is not a usable number.
    This function does not prove who sent a message.
    """

    if not isinstance(raw, str):
        raise CustomerPhoneError("invalid_phone")
    text = raw.strip()
    if not text:
        raise CustomerPhoneError("invalid_phone")
    if "@" in text:
        raise CustomerPhoneError("provider_identifier")
    if re.search(r"[A-Za-z]", text):
        raise CustomerPhoneError("invalid_phone")

    compact = _SEPARATORS.sub("", text)
    if compact.startswith("+"):
        return _from_explicit_digits(compact[1:])
    if compact.startswith("00"):
        return _from_explicit_digits(compact[2:])
    if not compact.isdigit():
        raise CustomerPhoneError("invalid_phone")
    if compact.startswith(_SYRIA_COUNTRY):
        return _syrian_e164(compact)
    national = compact[1:] if compact.startswith("0") else compact
    if len(national) == _SYRIA_NATIONAL_LENGTH and national.startswith("9"):
        return _syrian_e164(_SYRIA_COUNTRY + national)
    raise CustomerPhoneError("invalid_phone")


def _from_explicit_digits(digits: str) -> str:
    if not digits.isdigit():
        raise CustomerPhoneError("invalid_phone")
    if digits.startswith(_SYRIA_COUNTRY):
        return _syrian_e164(digits)
    if _E164_DIGITS.fullmatch(digits) is None:
        raise CustomerPhoneError("invalid_phone")
    return f"+{digits}"


def _syrian_e164(digits: str) -> str:
    national = digits[len(_SYRIA_COUNTRY) :]
    if (
        not digits.startswith(_SYRIA_COUNTRY)
        or len(digits) != len(_SYRIA_COUNTRY) + _SYRIA_NATIONAL_LENGTH
        or len(national) != _SYRIA_NATIONAL_LENGTH
        or not national.startswith("9")
    ):
        raise CustomerPhoneError("invalid_phone")
    return f"+{digits}"


__all__ = ["CustomerPhoneError", "normalize_customer_phone"]
