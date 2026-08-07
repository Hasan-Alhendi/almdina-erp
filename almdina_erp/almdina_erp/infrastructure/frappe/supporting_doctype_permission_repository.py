from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import frappe
from frappe.permissions import setup_custom_perms

from almdina_erp.almdina_erp.application.security.supporting_doctype_permissions import (
    SUPPORTING_DOCTYPES,
    supporting_field_permission_projection,
    supporting_standard_permission_projection,
)


class SupportingDoctypePermissionRepository:
    """Persist native Frappe rights required by capability-backed resources."""

    @staticmethod
    def _ensure_custom_baseline(doctype: str) -> None:
        if frappe.db.exists("Custom DocPerm", {"parent": doctype}):
            return
        if not frappe.db.exists("DocPerm", {"parent": doctype}):
            return
        setup_custom_perms(doctype)

    @staticmethod
    def _blank_override(doctype: str, role: str, permlevel: int = 0) -> Any:
        return frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": permlevel,
                "if_owner": 0,
            }
        )

    def _save_rights(
        self,
        *,
        doctype: str,
        role: str,
        permlevel: int,
        rights: Mapping[str, bool],
    ) -> None:
        row_names = frappe.get_all(
            "Custom DocPerm",
            filters={
                "parent": doctype,
                "role": role,
                "permlevel": permlevel,
                "if_owner": 0,
            },
            pluck="name",
            order_by="creation asc",
        )
        enabled = any(bool(value) for value in rights.values())
        if not row_names and not enabled:
            return

        documents = [
            frappe.get_doc("Custom DocPerm", name) for name in row_names
        ] or [self._blank_override(doctype, role, permlevel)]
        for document in documents:
            for permission_type, value in rights.items():
                if document.meta.has_field(permission_type):
                    document.set(permission_type, int(bool(value)))
            if document.is_new():
                document.insert(ignore_permissions=True)
            else:
                document.save(ignore_permissions=True)

    def save_role_state(
        self,
        role: str,
        state: Mapping[str, Any] | None,
    ) -> None:
        """Persist only native supporting rights; business state stays canonical."""

        for doctype in SUPPORTING_DOCTYPES:
            if not frappe.db.exists("DocType", doctype):
                continue
            self._ensure_custom_baseline(doctype)
            standard = supporting_standard_permission_projection(doctype, state)
            if standard:
                self._save_rights(
                    doctype=doctype,
                    role=role,
                    permlevel=0,
                    rights=standard,
                )
            for permlevel, rights in supporting_field_permission_projection(
                doctype,
                state,
            ).items():
                self._save_rights(
                    doctype=doctype,
                    role=role,
                    permlevel=permlevel,
                    rights=rights,
                )
            frappe.clear_cache(doctype=doctype)

        users = frappe.get_all(
            "Has Role",
            filters={
                "parenttype": "User",
                "role": role,
            },
            pluck="parent",
        )
        for user in set(str(value) for value in users if value):
            frappe.clear_cache(user=user)


__all__ = ["SupportingDoctypePermissionRepository"]
