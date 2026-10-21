"""Read the exact, currently approved customer-owned cutting plan."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.customer_bot.approved_plan_service import (
    CustomerBotApprovedPlanSnapshot,
)
from almdina_erp.almdina_erp.application.customer_bot.resolve_customer_identity import (
    resolve_customer_identity,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import IdentityCode
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    plan_read_requires_current_revision,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import SYSTEM, UPLOADED_DXF
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    approved_plan_for_order,
    production_plan_facts,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_phone_directory import (
    FrappeCustomerPhoneDirectory,
)


class FrappeCustomerBotApprovedPlanReader:
    """Resolve primary-phone ownership before reading any plan details."""

    def read(self, phone: str, order_name: str) -> CustomerBotApprovedPlanSnapshot | None:
        identity = _identity(phone)
        name = _exact_order_name(order_name)
        if identity is None or name is None:
            return None

        header = frappe.db.get_value(
            "Door Cutting Order",
            {"name": name, "customer": identity},
            ["name", "status", "revision_state"],
            as_dict=True,
        )
        if not header:
            return None
        status = str(header.get("status") or "").strip()
        revision_state = str(header.get("revision_state") or "")
        if status == "Cancelled":
            return CustomerBotApprovedPlanSnapshot(available=False, cancelled=True)
        if plan_read_requires_current_revision(status, revision_state):
            return None

        try:
            order = frappe.get_doc("Door Cutting Order", name)
            if str(getattr(order, "customer", None) or "") != identity:
                return None
            status = str(getattr(order, "status", None) or "").strip()
            if status == "Cancelled":
                return CustomerBotApprovedPlanSnapshot(available=False, cancelled=True)
            if plan_read_requires_current_revision(
                status, str(getattr(order, "revision_state", None) or "")
            ):
                return None

            plan = approved_plan_for_order(order)
            if plan is None:
                return None
            facts = production_plan_facts(order)
            if not facts.has_approved_plan or facts.approved_plan_name != plan.name:
                return None

            source_type = str(getattr(plan, "source_type", None) or SYSTEM).strip()
            if source_type not in {SYSTEM, UPLOADED_DXF}:
                return None
            if source_type == UPLOADED_DXF:
                if (
                    not str(getattr(plan, "dxf_file", None) or "").strip()
                    or str(getattr(plan, "dxf_status", None) or "").strip() != "Validated"
                ):
                    return None
            if not _has_printable_snapshot(plan):
                return None

            return CustomerBotApprovedPlanSnapshot(
                available=True,
                plan_name=str(plan.name),
                revision=int(getattr(plan, "revision", None) or 1),
                source_type=source_type,
                consistency_key=_consistency_key(order, plan),
            )
        except Exception:
            # Missing, foreign, stale, incomplete, and contradictory plans are
            # intentionally indistinguishable to the customer.
            return None


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


def _has_printable_snapshot(plan: Any) -> bool:
    snapshot = str(getattr(plan, "snapshot_json", None) or "").strip()
    if not snapshot:
        return False
    parsed = frappe.parse_json(snapshot) or {}
    if not isinstance(parsed, dict):
        return False
    sources = getattr(plan, "sources", None) or []
    return bool(sources)


def _consistency_key(order: Any, plan: Any) -> str:
    payload = {
        "order": {
            "name": str(getattr(order, "name", "") or ""),
            "modified": str(getattr(order, "modified", "") or ""),
            "revision": str(getattr(order, "revision", "") or ""),
            "approved_plan": str(getattr(order, "approved_plan", "") or ""),
        },
        "plan": _json_safe(getattr(plan, "as_dict", lambda: {})()),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "as_dict") and callable(value.as_dict):
        return _json_safe(value.as_dict())
    return value


__all__ = ["FrappeCustomerBotApprovedPlanReader"]
