"""Retired additional-phone linking commands.

Customer identity uses the current primary mobile number only. These
functions stay importable so an older caller fails closed and does not
create or change a grant.
"""

from __future__ import annotations


class PhoneAccessRetired(RuntimeError):
    """Additional-phone request, approval, rejection, and revocation are retired."""


def _retired() -> None:
    raise PhoneAccessRetired(
        "Additional phone linking is retired. "
        "Customer identity uses the current primary mobile number only."
    )


def request_additional_phone_access(*_args: object, **_kwargs: object) -> None:
    _retired()


def approve_phone_access_request(*_args: object, **_kwargs: object) -> None:
    _retired()


def reject_phone_access_request(*_args: object, **_kwargs: object) -> None:
    _retired()


def revoke_phone_access(*_args: object, **_kwargs: object) -> None:
    _retired()


__all__ = [
    "PhoneAccessRetired",
    "approve_phone_access_request",
    "reject_phone_access_request",
    "request_additional_phone_access",
    "revoke_phone_access",
]
