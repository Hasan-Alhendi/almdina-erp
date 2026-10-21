"""Read measurements saved on one customer-owned order.

The read resolves the current primary phone, then loads only the fields the
customer measurements document prints. It does not save, recalculate, or lock
the order.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.customer_bot.measurements_service import (
    CustomerBotMeasurementsSnapshot,
)
from almdina_erp.almdina_erp.application.customer_bot.resolve_customer_identity import (
    resolve_customer_identity,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import IdentityCode
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    plan_read_requires_current_revision,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)
from almdina_erp.almdina_erp.infrastructure.printing.measurements_print_document import (
    PRINT_ORDER_FIELDS,
    PRINT_PIECE_FIELDS,
    order_print_payload,
)


_HEADER_FIELDS = tuple(dict.fromkeys((*PRINT_ORDER_FIELDS, "status", "revision_state")))
# drawing_json and geometry_json are print aliases, not stored columns.
_PIECE_FIELDS = tuple(
    field
    for field in PRINT_PIECE_FIELDS
    if field not in {"drawing_json", "geometry_json"}
)
_DETAIL_DOCTYPE = "Door Cutting Order Detail"
_ORDER_DOCTYPE = "Door Cutting Order"


@dataclass(frozen=True, slots=True)
class OwnedMeasurementSource:
    order_name: str
    phone: str
    payload: dict[str, Any]
    consistency_key: str
    cancelled: bool = False


class FrappeCustomerBotMeasurementsReader:
    """Resolve primary-phone ownership before reading any measurement rows."""

    def read(self, phone: str, order_name: str) -> CustomerBotMeasurementsSnapshot | None:
        source = load_owned_measurement_source(phone, order_name)
        if source is None:
            return None
        if source.cancelled:
            return CustomerBotMeasurementsSnapshot(available=False, cancelled=True)
        pieces = source.payload.get("pieces") or []
        if not pieces:
            return CustomerBotMeasurementsSnapshot(available=False)
        return CustomerBotMeasurementsSnapshot(
            available=True,
            order_name=source.order_name,
            consistency_key=source.consistency_key,
        )


def load_owned_measurement_source(phone: str, order_name: str) -> OwnedMeasurementSource | None:
    identity = _identity(phone)
    name = _exact_order_name(order_name)
    if identity is None or name is None:
        return None

    header = frappe.db.get_value(
        _ORDER_DOCTYPE,
        {"name": name, "customer": identity},
        list(_HEADER_FIELDS),
        as_dict=True,
    )
    if not header:
        return None
    status = str(header.get("status") or "").strip()
    revision_state = str(header.get("revision_state") or "")
    if status == "Cancelled":
        return OwnedMeasurementSource(
            order_name=name,
            phone="",
            payload={},
            consistency_key="",
            cancelled=True,
        )
    if plan_read_requires_current_revision(status, revision_state):
        return None

    customer_phone = str(frappe.db.get_value("Customer", identity, "mobile_no") or "").strip()
    pieces = _piece_rows(name)
    payload = order_print_payload({**header, "pieces": pieces})
    return OwnedMeasurementSource(
        order_name=str(header.get("name") or name),
        phone=customer_phone,
        payload=payload,
        consistency_key=_consistency_key(
            customer=identity,
            phone=customer_phone,
            status=status,
            revision_state=revision_state,
            payload=payload,
        ),
    )


def _piece_rows(order_name: str) -> list[dict[str, Any]]:
    columns = ", ".join(f"`{field}`" for field in _PIECE_FIELDS)
    rows = frappe.db.sql(
        f"""select {columns}
            from `tab{_DETAIL_DOCTYPE}`
            where parent=%s and parenttype=%s
            order by idx asc""",
        (order_name, _ORDER_DOCTYPE),
        as_dict=True,
    )
    return [dict(row) for row in rows]


def _identity(phone: str) -> str | None:
    identity = resolve_customer_identity(FrappeCustomerPhoneDirectory(), phone)
    if identity.code != IdentityCode.ALLOWED:
        return None
    return identity.customer_id


def _exact_order_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or any(character.isspace() for character in name):
        return None
    if any(character in name for character in "%_*?"):
        return None
    return name


def _consistency_key(
    *,
    customer: str,
    phone: str,
    status: str,
    revision_state: str,
    payload: dict[str, Any],
) -> str:
    material = {
        "customer": customer,
        "phone": phone,
        "status": status,
        "revision_state": revision_state,
        "payload": payload,
    }
    encoded = json.dumps(
        material,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "FrappeCustomerBotMeasurementsReader",
    "OwnedMeasurementSource",
    "load_owned_measurement_source",
]
