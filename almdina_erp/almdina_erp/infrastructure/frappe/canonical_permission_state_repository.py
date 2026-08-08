from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import frappe

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)


STATE_DOCTYPE = "Almdina Role Capability State"
AUDIT_DOCTYPE = "Almdina Permission Audit"


class CanonicalPermissionStateRepository:
    """Persist the sole authoritative Almdina capability state per role.

    Frappe DocPerm and Custom DocPerm are projections only. They must never be
    read back as business authority, because legacy/native permission rows can
    otherwise silently widen factory access during migrate or permission setup.
    """

    @staticmethod
    def _empty_state() -> dict[str, bool]:
        return normalize_capability_state({})

    @staticmethod
    def _decode(raw: str | Mapping[str, Any] | None) -> dict[str, bool]:
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
        if not isinstance(payload, dict):
            payload = {}
        return normalize_capability_state(payload)

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

        normalized = normalize_capability_state(state)
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
        """Return the last explicitly audited matrix state, if one exists."""

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
        return self._decode(rows[0].get("after_json"))

    def bootstrap_fail_closed(self, role: str) -> dict[str, bool]:
        """Create canonical state from explicit audit provenance or deny-all.

        Legacy/native DocPerm rows are intentionally ignored. Without an Almdina
        audit record there is no trustworthy evidence that a business capability
        was explicitly granted through the factory matrix, so migration fails
        closed instead of resurrecting historical Frappe permissions.
        """

        resolved = str(role or "").strip()
        if self.exists(resolved):
            return self.read(resolved)
        audited = self.latest_audited_state(resolved)
        return self.save(resolved, audited if audited is not None else {})


__all__ = [
    "AUDIT_DOCTYPE",
    "CanonicalPermissionStateRepository",
    "STATE_DOCTYPE",
]
