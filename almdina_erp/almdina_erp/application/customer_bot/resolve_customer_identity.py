"""Resolve a phone against current customer data and additional-phone grants.

Passing an E.164 string does not prove the sender. The gateway adapter must
do that before this use case runs. There is no verified flag to set.
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

from .phone_access_ports import CustomerPhoneDirectory, PhoneAccessStore


def resolve_customer_identity(
    directory: CustomerPhoneDirectory,
    store: PhoneAccessStore,
    phone: str,
) -> CustomerIdentity:
    try:
        normalized = normalize_customer_phone(phone)
    except CustomerPhoneError as error:
        return CustomerIdentity(error.code)
    primary_customer_ids = directory.find_by_normalized_phone(normalized)
    access = store.get_access_by_phone(normalized)
    grant_customer_exists = bool(
        access is not None and directory.customer_exists(access.customer_id)
    )
    return decide_customer_identity(
        primary_customer_ids,
        access,
        grant_customer_exists=grant_customer_exists,
    )


__all__ = ["resolve_customer_identity"]
