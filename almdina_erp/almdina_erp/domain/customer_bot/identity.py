"""Match one normalized phone to at most one current customer primary number.

The result carries the customer id only when exactly one current
``Customer.mobile_no`` matches. It does not carry orders, prices, or a
display name. A historical additional-phone grant is not an access basis.
"""

from __future__ import annotations

from dataclasses import dataclass

class IdentityCode:
    ALLOWED = "allowed"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    INVALID_PHONE = "invalid_phone"
    PROVIDER_IDENTIFIER = "provider_identifier"


class AccessBasis:
    PRIMARY = "primary"
    # Kept so older callers can name the retired basis. It is not a valid
    # result: an additional-phone grant never authorizes identity.
    ADDITIONAL = "additional"


@dataclass(frozen=True, slots=True)
class CustomerIdentity:
    code: str
    customer_id: str | None = None
    access_basis: str | None = None

    def __post_init__(self) -> None:
        if self.code == IdentityCode.ALLOWED:
            if not self.customer_id or self.access_basis != AccessBasis.PRIMARY:
                raise ValueError("an allowed identity needs the current primary customer")
            return
        if self.customer_id is not None or self.access_basis is not None:
            raise ValueError("a refused identity cannot carry a customer")


def decide_customer_identity(
    primary_customer_ids: tuple[str, ...] | list[str],
) -> CustomerIdentity:
    """Resolve access from every current primary-phone match.

    Zero matches are unknown. More than one match is a conflict. Neither
    result includes a customer id. Additional-phone grants are ignored.
    """

    distinct: list[str] = []
    for customer_id in primary_customer_ids:
        if customer_id not in distinct:
            distinct.append(customer_id)
    if len(distinct) > 1:
        return CustomerIdentity(IdentityCode.CONFLICT)
    if len(distinct) == 1:
        return CustomerIdentity(
            IdentityCode.ALLOWED,
            distinct[0],
            AccessBasis.PRIMARY,
        )
    return CustomerIdentity(IdentityCode.UNKNOWN)


__all__ = [
    "AccessBasis",
    "CustomerIdentity",
    "IdentityCode",
    "decide_customer_identity",
]
