"""Ports for customer identity and additional-phone access.

Stores and the customer directory are injected. They do not carry provider
session ids or connection secrets.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from almdina_erp.almdina_erp.domain.customer_bot.phone_access import (
    StoredPhoneAccess,
    StoredPhoneRequest,
)


class CustomerPhoneDirectory(Protocol):
    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]: ...

    def customer_exists(self, customer_id: str) -> bool: ...


class CustomerBotActorPolicy(Protocol):
    def has_manage_access(self, actor_id: str) -> bool: ...

    def can_access_customer(self, actor_id: str, customer_id: str) -> bool: ...


class PhoneAccessStore(Protocol):
    def exclusive(self) -> AbstractContextManager[None]: ...

    def lock_request(self, request_id: str) -> StoredPhoneRequest | None: ...

    def lock_access_by_phone(self, normalized_phone: str) -> StoredPhoneAccess | None: ...

    def pending_for_phone(self, normalized_phone: str) -> StoredPhoneRequest | None: ...

    def get_access_by_phone(self, normalized_phone: str) -> StoredPhoneAccess | None: ...

    def insert_request(self, request: StoredPhoneRequest) -> StoredPhoneRequest: ...

    def save_request(self, request: StoredPhoneRequest) -> StoredPhoneRequest: ...

    def insert_access(self, access: StoredPhoneAccess) -> StoredPhoneAccess: ...

    def save_access(self, access: StoredPhoneAccess) -> StoredPhoneAccess: ...


__all__ = [
    "CustomerBotActorPolicy",
    "CustomerPhoneDirectory",
    "PhoneAccessStore",
]
