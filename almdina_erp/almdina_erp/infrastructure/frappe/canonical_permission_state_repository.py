from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.business_capability_state import (
    normalize_business_capability_state,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import ALL_CAPABILITIES


STATE_DOCTYPE = "Almdina Role Capability State"
AUDIT_DOCTYPE = "Almdina Permission Audit"


class CanonicalPermissionStateRepository:
    """Persist the sole authoritative Almdina capability state per role.

    Frappe DocPerm, Custom DocPerm, and historical audit rows are never business
    authority. They exist only for runtime projection or historical inspection.
    Missing canonical state always fails closed to an empty matrix.
    """

    @staticmethod
    def _empty_state() -> dict[str, bool]:
        return normalize_business_capability_state({})

    @staticmethod
    def _payload(raw: str | Mapping[str, Any] | None) -> dict[str, Any]:
        if isinstance(raw, Mapping):
            payload: Any = dict(raw)
        else:
            text = str(raw or "").strip()
            if not text:
                payload = {}
            else:
                try:
                    payload = json.loads(text)
                except (TypeError, ValueError, json.JSONDecodeError):
                    payload = {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _decode(cls, raw: str | Mapping[str, Any] | None) -> dict[str, bool]:
        """Decode current canonical business state strictly.

        Unknown capability keys remain an error for canonical state. Lookup-only
        dependencies are not promoted to explicit Customer/Edge administration
        grants when state is read back.
        """

        return normalize_business_capability_state(cls._payload(raw))

    @classmethod
    def _decode_legacy_audit(
        cls,
        raw: str | Mapping[str, Any] | None,
    ) -> dict[str, bool]:
        """Decode historical audit JSON for display/inspection only.

        Older releases wrote broad keys that no longer exist after the granular
        permission redesign. Unknown historical keys are ignored so immutable
        audit rows remain readable, but this decoder is never used to bootstrap
        business authority.
        """

        payload = cls._payload(raw)
        current_only = {
            str(key): value
            for key, value in payload.items()
            if str(key) in ALL_CAPABILITIES
        }
        return normalize_capability_state(current_only)

    def available(self) -> bool:
        return bool(frappe.db.exists("DocType", STATE_DOCTYPE))

    def exists(self, role: str) -> bool:
        return bool(
            self.available()
            and frappe.db.exists(STATE_DOCTYPE, {"role": str(role or "").strip()})
        )

    def read(self, role: str) -> dict[str, bool]:
        resolved = str(role or "").strip()
        if not resolved or not self.available():
            return self._empty_state()
        name = frappe.db.exists(STATE_DOCTYPE, {"role": resolved})
        if not name:
            return self._empty_state()
        raw = frappe.db.get_value(STATE_DOCTYPE, name, "capabilities_json")
        return self._decode(raw)

    def save(self, role: str, state: Mapping[str, Any] | None) -> dict[str, bool]:
        resolved = str(role or "").strip()
        if not resolved:
            raise ValueError("Role is required.")
        if not self.available():
            raise RuntimeError(f"{STATE_DOCTYPE} is not installed.")

        normalized = normalize_business_capability_state(state)
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
        name = frappe.db.exists(STATE_DOCTYPE, {"role": resolved})
        if name:
            frappe.db.set_value(
                STATE_DOCTYPE,
                name,
                "capabilities_json",
                encoded,
                update_modified=True,
            )
        else:
            frappe.get_doc(
                {
                    "doctype": STATE_DOCTYPE,
                    "role": resolved,
                    "capabilities_json": encoded,
                }
            ).insert(ignore_permissions=True)
        return normalized

    def latest_audited_state(self, role: str) -> dict[str, bool] | None:
        """Return the last audited snapshot for historical inspection only."""

        resolved = str(role or "").strip()
        if not resolved or not frappe.db.exists("DocType", AUDIT_DOCTYPE):
            return None
        rows = frappe.get_all(
            AUDIT_DOCTYPE,
            filters={"role": resolved},
            fields=["after_json"],
            order_by="changed_on desc, creation desc",
            limit_page_length=1,
        )
        if not rows:
            return None
        return self._decode_legacy_audit(rows[0].get("after_json"))

    def bootstrap_fail_closed(self, role: str) -> dict[str, bool]:
        """Create missing canonical state as deny-all.

        The Permission Matrix is the only business authority. Historical audit
        records and Frappe permission projections must never resurrect grants
        automatically during migrate or permission synchronization.
        """

        resolved = str(role or "").strip()
        if self.exists(resolved):
            return self.read(resolved)
        return self.save(resolved, {})


__all__ = [
    "AUDIT_DOCTYPE",
    "CanonicalPermissionStateRepository",
    "STATE_DOCTYPE",
]
