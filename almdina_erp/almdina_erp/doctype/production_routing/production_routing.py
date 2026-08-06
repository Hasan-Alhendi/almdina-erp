from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.security.role_management import (
    PROTECTED_ROLE_NAMES,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    audit_deleted_document,
    audit_saved_document,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_references import (
    find_link_references,
    reference_summary,
)
from almdina_erp.almdina_erp.infrastructure.frappe.routing_role_codec import (
    decode_eligible_roles,
    eligible_roles_display,
    encode_eligible_roles,
)


class ProductionRouting(Document):
    def validate(self) -> None:
        if not self.stages:
            frappe.throw(_("Production Routing requires at least one stage."))

        sequences: set[int] = set()
        stage_types: set[str] = set()
        required_count = 0
        prepared: list[tuple[object, tuple[str, ...]]] = []
        ordered = sorted(self.stages, key=lambda row: cint(row.sequence))
        for index, row in enumerate(ordered, start=1):
            row.stage_type = str(row.stage_type or "").strip()
            row.department_label = str(row.department_label or "").strip()
            sequence = cint(row.sequence)
            if sequence <= 0:
                frappe.throw(_("Routing stage sequence must be greater than zero."))
            if sequence in sequences:
                frappe.throw(_("Routing stage sequence {0} is duplicated.").format(sequence))
            if not row.stage_type:
                frappe.throw(_("Routing stage code is required."))
            if row.stage_type in stage_types:
                frappe.throw(_("Routing stage {0} is duplicated.").format(row.stage_type))

            roles = self._stage_roles(row)
            if cint(row.required):
                required_count += 1
                if not row.department_label:
                    frappe.throw(
                        _("Department label is required for stage {0}.").format(
                            row.stage_type
                        )
                    )
                if not roles:
                    frappe.throw(
                        _("Choose at least one eligible role for stage {0}.").format(
                            row.stage_type
                        )
                    )
            prepared.append((row, roles))
            sequences.add(sequence)
            stage_types.add(row.stage_type)
            row.idx = index
        if not required_count:
            frappe.throw(_("Production Routing requires at least one required stage."))

        # Every route save and role rename locks the same Role rows in sorted
        # order. A concurrent save therefore either finishes before the rename
        # (and is included in it) or validates after the old role no longer exists.
        self._lock_roles(
            tuple(role for _row, roles in prepared for role in roles)
        )
        for row, roles in prepared:
            self._validate_roles(roles, stage_type=row.stage_type)
            row.eligible_roles_json = encode_eligible_roles(roles)
            row.eligible_roles_display = eligible_roles_display(roles)
            # Keep the first role only as a read-only compatibility snapshot for
            # older reports and in-flight records. New authorization uses all roles.
            row.operational_role = roles[0] if roles else ""

        self._prevent_active_route_mutation()

    @staticmethod
    def _stage_roles(row) -> tuple[str, ...]:
        try:
            return decode_eligible_roles(
                getattr(row, "eligible_roles_json", None),
                legacy_role=getattr(row, "operational_role", None),
            )
        except ValueError as error:
            frappe.throw(_(str(error)), frappe.ValidationError)
        raise AssertionError("frappe.throw must interrupt execution")

    @staticmethod
    def _lock_roles(roles: tuple[str, ...]) -> None:
        for role in sorted(set(roles)):
            frappe.db.sql(
                "select name from `tabRole` where name = %s for update",
                (role,),
            )

    @staticmethod
    def _validate_roles(roles: tuple[str, ...], *, stage_type: str) -> None:
        for role in roles:
            if role in PROTECTED_ROLE_NAMES:
                frappe.throw(
                    _("Role {0} is protected and cannot be used for stage {1}.").format(
                        role,
                        stage_type,
                    ),
                    frappe.ValidationError,
                )
            values = frappe.db.get_value(
                "Role",
                role,
                ["disabled", "desk_access"],
                as_dict=True,
            )
            if not values:
                frappe.throw(
                    _("Eligible role {0} does not exist.").format(role),
                    frappe.ValidationError,
                )
            if cint(values.disabled):
                frappe.throw(
                    _("Eligible role {0} is disabled.").format(role),
                    frappe.ValidationError,
                )
            if not cint(values.desk_access):
                frappe.throw(
                    _("Eligible role {0} does not allow Desk access.").format(role),
                    frappe.ValidationError,
                )

    def _prevent_active_route_mutation(self) -> None:
        """Keep an in-flight order on the route definition it was dispatched with."""

        if self.is_new() or not frappe.db.exists("Production Routing", self.name):
            return
        previous_disabled = cint(
            frappe.db.get_value("Production Routing", self.name, "disabled")
        )
        previous_rows = frappe.get_all(
            "Production Routing Stage",
            filters={"parent": self.name, "parenttype": "Production Routing"},
            fields=[
                "sequence",
                "stage_type",
                "department_label",
                "eligible_roles_json",
                "operational_role",
                "required",
            ],
            order_by="sequence asc, idx asc",
        )
        previous = [
            (
                cint(row.sequence),
                str(row.stage_type or ""),
                str(row.department_label or ""),
                decode_eligible_roles(
                    row.eligible_roles_json,
                    legacy_role=row.operational_role,
                ),
                cint(row.required),
            )
            for row in previous_rows
        ]
        current = [
            (
                cint(row.sequence),
                str(row.stage_type or ""),
                str(row.department_label or ""),
                self._stage_roles(row),
                cint(row.required),
            )
            for row in sorted(self.stages or (), key=lambda item: cint(item.sequence))
        ]
        changed = previous != current or (not previous_disabled and cint(self.disabled))
        if not changed:
            return
        active = frappe.db.exists(
            "Door Cutting Order",
            {
                "production_path": self.name,
                "current_production_stage": ["is", "set"],
                "status": ["not in", ["Delivered", "Cancelled"]],
            },
        )
        if active:
            frappe.throw(
                _(
                    "This route is used by active orders. Finish, cancel, or return those orders before changing its stages."
                ),
                frappe.ValidationError,
            )

    def before_trash(self) -> None:
        references = find_link_references(self.doctype, self.name)
        if references:
            frappe.throw(
                _("This production routing is in use and cannot be deleted: {0}").format(
                    reference_summary(references)
                ),
                frappe.ValidationError,
            )

    def on_update(self) -> None:
        audit_saved_document(self)

    def on_trash(self) -> None:
        audit_deleted_document(self)


__all__ = ["ProductionRouting"]
