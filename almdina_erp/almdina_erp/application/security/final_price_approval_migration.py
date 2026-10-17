"""Idempotent helpers for final-price approval phase-1 install.

Does not grant ``approve_final_price`` or ``cancel_final_price_approval`` to
any role and never creates approval records. Existing role grants remain
untouched when migrate runs again.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_STATUS_UNAPPROVED,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def legacy_orders_remain_unapproved(
    *,
    plan_approved: bool = False,
    customer_quote_status: str | None = None,
) -> str:
    """Old plan/special-quote approvals must never imply final price approval."""

    del plan_approved, customer_quote_status
    return PRICE_APPROVAL_STATUS_UNAPPROVED


def capability_is_ungranted_by_default(state: Mapping[str, Any] | None) -> bool:
    """Confirm the new capability stays off unless an admin grants it explicitly."""

    return (state or {}).get(Capability.APPROVE_FINAL_PRICE) is not True


def cancel_capability_is_ungranted_by_default(state: Mapping[str, Any] | None) -> bool:
    """The cancel capability stays off unless an administrator grants it explicitly."""

    return (state or {}).get(Capability.CANCEL_FINAL_PRICE_APPROVAL) is not True


def preserve_cancel_capability_grants(
    before: Mapping[str, Any] | None,
    after_sync: Mapping[str, Any] | None,
) -> bool:
    """Re-running sync must not clear an administrator grant of price-approval cancellation."""

    before_state = dict(before or {})
    after_state = dict(after_sync or {})
    if before_state.get(Capability.CANCEL_FINAL_PRICE_APPROVAL) is True:
        return after_state.get(Capability.CANCEL_FINAL_PRICE_APPROVAL) is True
    return after_state.get(Capability.CANCEL_FINAL_PRICE_APPROVAL) is not True


def preserve_existing_capability_grants(
    before: Mapping[str, Any] | None,
    after_sync: Mapping[str, Any] | None,
) -> bool:
    """Re-running install must not clear an admin grant that already exists."""

    before_state = dict(before or {})
    after_state = dict(after_sync or {})
    if before_state.get(Capability.APPROVE_FINAL_PRICE) is True:
        return after_state.get(Capability.APPROVE_FINAL_PRICE) is True
    return after_state.get(Capability.APPROVE_FINAL_PRICE) is not True


__all__ = [
    "cancel_capability_is_ungranted_by_default",
    "capability_is_ungranted_by_default",
    "legacy_orders_remain_unapproved",
    "preserve_cancel_capability_grants",
    "preserve_existing_capability_grants",
]
