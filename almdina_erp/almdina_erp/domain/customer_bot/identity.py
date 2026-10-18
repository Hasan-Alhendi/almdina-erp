"""Match one normalized phone to at most one customer.

The result carries the customer id and why access is allowed or refused.
It does not carry orders, prices, or a display name. A conflict refuses
every match instead of keeping the first row.
"""

from __future__ import annotations

from dataclasses import dataclass

from .phone_access import AccessStatus, StoredPhoneAccess


class IdentityCode:
    ALLOWED = "allowed"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    INVALID_PHONE = "invalid_phone"
    PROVIDER_IDENTIFIER = "provider_identifier"


class AccessBasis:
    PRIMARY = "primary"
    ADDITIONAL = "additional"


@dataclass(frozen=True, slots=True)
class CustomerIdentity:
    code: str
    customer_id: str | None = None
    access_basis: str | None = None

    def __post_init__(self) -> None:
        if self.code == IdentityCode.ALLOWED:
            if not self.customer_id or self.access_basis not in {
                AccessBasis.PRIMARY,
                AccessBasis.ADDITIONAL,
            }:
                raise ValueError("an allowed identity needs a customer and a basis")
            return
        if self.customer_id is not None or self.access_basis is not None:
            raise ValueError("a refused identity cannot carry a customer")


def decide_customer_identity(
    primary_customer_ids: tuple[str, ...] | list[str],
    access: StoredPhoneAccess | None,
    *,
    grant_customer_exists: bool,
) -> CustomerIdentity:
    """Resolve access from the current customer phones and one grant row.

    ``primary_customer_ids`` must already be every current match. Revoked
    grants do not authorize. An active grant for a different customer than
    the current primary match is a conflict.
    """

    distinct: list[str] = []
    for customer_id in primary_customer_ids:
        if customer_id not in distinct:
            distinct.append(customer_id)
    if len(distinct) > 1:
        return CustomerIdentity(IdentityCode.CONFLICT)

    primary_id = distinct[0] if distinct else None
    active_grant = (
        access is not None
        and access.status == AccessStatus.ACTIVE
        and grant_customer_exists
    )
    if active_grant and primary_id is not None and access is not None and access.customer_id != primary_id:
        return CustomerIdentity(IdentityCode.CONFLICT)
    if primary_id is not None:
        return CustomerIdentity(
            IdentityCode.ALLOWED,
            primary_id,
            AccessBasis.PRIMARY,
        )
    if active_grant and access is not None:
        return CustomerIdentity(
            IdentityCode.ALLOWED,
            access.customer_id,
            AccessBasis.ADDITIONAL,
        )
    return CustomerIdentity(IdentityCode.UNKNOWN)


__all__ = [
    "AccessBasis",
    "CustomerIdentity",
    "IdentityCode",
    "decide_customer_identity",
]
