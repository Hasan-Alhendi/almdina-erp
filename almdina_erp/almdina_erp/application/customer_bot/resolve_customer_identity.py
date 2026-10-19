"""Resolve a phone against the current customer primary number only.

Passing an E.164 string does not prove the sender. The gateway adapter must
do that before this use case runs. There is no verified flag to set.
An additional-phone grant is not consulted.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.customer_bot.identity import (
    CustomerIdentity,
    decide_customer_identity,
)
from almdina_erp.almdina_erp.domain.customer_bot.phone_number import (
    CustomerPhoneError,
    normalize_customer_phone,
)

from .phone_access_ports import CustomerPhoneDirectory


def resolve_customer_identity(
    directory: CustomerPhoneDirectory,
    phone: str,
) -> CustomerIdentity:
    try:
        normalized = normalize_customer_phone(phone)
    except CustomerPhoneError as error:
        return CustomerIdentity(error.code)
    return decide_customer_identity(directory.find_by_normalized_phone(normalized))


__all__ = ["resolve_customer_identity"]
