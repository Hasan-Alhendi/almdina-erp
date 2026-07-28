from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.orders.revisions import (
    RevisionActivationNotAllowed,
    RevisionState,
    assert_revision_activation_allowed,
    assert_revision_dispatchable,
    revision_root,
)


@dataclass(frozen=True, slots=True)
class RevisionActivationContext:
    predecessor_name: str
    predecessor_plan: str | None
    revision_root: str
    released_material_reservations: tuple[str, ...]
    released_remnants: tuple[str, ...]


def _throw_domain_error(exc: RevisionActivationNotAllowed) -> None:
    frappe.throw(_(str(exc)))


def _lock_order_rows(*names: str) -> None:
    for name in sorted({str(name or "").strip() for name in names if name}):
        frappe.db.sql(
            "select name from `tabDoor Cutting Order` where name = %s for update",
            (name,),
        )


def load_locked_revision_order(order_name: str) -> Any:
    """Lock a complete revision chain in deterministic name order and reload it."""

    identity = frappe.db.get_value(
        "Door Cutting Order",
        order_name,
        ["revision_of", "revision_root"],
        as_dict=True,
    )
    if not identity:
        frappe.throw(_("Door Cutting Order {0} does not exist.").format(order_name))

    root_name = revision_root(
        order_name=str(identity.revision_of or order_name),
        current_root=identity.revision_root,
    )
    frappe.db.sql(
        """
        select name
          from `tabDoor Cutting Order`
         where name = %s
            or name = %s
            or revision_root = %s
         order by name asc
         for update
        """,
        (order_name, root_name, root_name),
    )
    return frappe.get_doc("Door Cutting Order", order_name)


def _has_open_stages(order_name: str) -> bool:
    return bool(
        frappe.db.exists(
            "Production Stage",
            {
                "door_cutting_order": order_name,
                "status": ["in", ["Pending", "In Progress", "Paused"]],
            },
        )
    )


def _has_material_activity(order_name: str) -> bool:
    return bool(
        frappe.db.exists(
            "Material Consumption Log",
            {
                "door_cutting_order": order_name,
                "status": "Submitted",
            },
        )
    )


def _competing_current_revision(
    *,
    root_name: str,
    predecessor_name: str,
    candidate_name: str,
) -> str | None:
    rows = frappe.db.sql(
        """
        select name
          from `tabDoor Cutting Order`
         where name not in (%s, %s)
           and (name = %s or revision_root = %s)
           and coalesce(nullif(revision_state, ''), 'Current') = 'Current'
         order by revision desc, creation desc
         limit 1
         for update
        """,
        (predecessor_name, candidate_name, root_name, root_name),
    )
    return str(rows[0][0]) if rows else None


def _other_current_revision(*, root_name: str, order_name: str) -> str | None:
    rows = frappe.db.sql(
        """
        select name
          from `tabDoor Cutting Order`
         where name != %s
           and (name = %s or revision_root = %s)
           and coalesce(nullif(revision_state, ''), 'Current') = 'Current'
         order by revision desc, creation desc
         limit 1
         for update
        """,
        (order_name, root_name, root_name),
    )
    return str(rows[0][0]) if rows else None


def _release_reserved_remnants(order_name: str) -> list[str]:
    names = frappe.get_all(
        "Board Remnant",
        filters={"status": "Reserved", "reserved_for_order": order_name},
        pluck="name",
    )
    released: list[str] = []
    for name in names:
        frappe.db.sql(
            "select name from `tabBoard Remnant` where name = %s for update",
            (name,),
        )
        current = frappe.db.get_value(
            "Board Remnant",
            name,
            ["status", "reserved_for_order"],
            as_dict=True,
        )
        if not current or current.status != "Reserved" or current.reserved_for_order != order_name:
            continue
        frappe.db.set_value(
            "Board Remnant",
            name,
            {
                "status": "Available",
                "reserved_for_order": None,
                "reservation_timestamp": None,
            },
            update_modified=True,
        )
        released.append(name)
    return released


def assert_order_revision_dispatchable(order: Any) -> None:
    competing = False
    has_revision_chain = any(
        str(getattr(order, fieldname, None) or "").strip()
        for fieldname in ("revision_of", "revision_root", "superseded_by")
    )
    if has_revision_chain:
        root_name = revision_root(
            order_name=str(getattr(order, "revision_of", None) or order.name),
            current_root=getattr(order, "revision_root", None),
        )
        competing = bool(
            _other_current_revision(root_name=root_name, order_name=order.name)
        )

    try:
        assert_revision_dispatchable(
            getattr(order, "revision_state", None),
            competing_current_revision=competing,
        )
    except RevisionActivationNotAllowed as exc:
        _throw_domain_error(exc)


def prepare_revision_activation(order: Any) -> RevisionActivationContext | None:
    """Retire reservations of a safe predecessor before plan approval.

    The surrounding Frappe request transaction guarantees that released
    reservations are restored automatically if plan creation, stock validation,
    or final activation fails later in the same request. The caller must load the
    order through ``load_locked_revision_order`` first.
    """

    predecessor_name = str(getattr(order, "revision_of", None) or "").strip()
    if not predecessor_name:
        return None

    root_name = revision_root(
        order_name=predecessor_name,
        current_root=getattr(order, "revision_root", None),
    )
    predecessor = frappe.get_doc("Door Cutting Order", predecessor_name)
    if predecessor.superseded_by and predecessor.superseded_by != order.name:
        frappe.throw(
            _("The previous revision is linked to a different successor: {0}").format(
                predecessor.superseded_by
            )
        )

    competing = _competing_current_revision(
        root_name=root_name,
        predecessor_name=predecessor.name,
        candidate_name=order.name,
    )
    predecessor_dispatched = bool(
        predecessor.production_path or predecessor.current_production_stage
    )
    predecessor_has_open_stages = _has_open_stages(predecessor.name)
    predecessor_has_material_activity = _has_material_activity(predecessor.name)

    try:
        assert_revision_activation_allowed(
            revision_of=predecessor_name,
            revision_state=getattr(order, "revision_state", None),
            predecessor_status=predecessor.status,
            predecessor_state=getattr(predecessor, "revision_state", None),
            predecessor_dispatched=predecessor_dispatched,
            predecessor_has_open_stages=predecessor_has_open_stages,
            predecessor_has_material_activity=predecessor_has_material_activity,
            competing_current_revision=bool(competing),
        )
    except RevisionActivationNotAllowed as exc:
        _throw_domain_error(exc)

    from almdina_erp.almdina_erp.services.stock_service import (
        transition_order_reservation,
    )

    released_material = transition_order_reservation(predecessor.name, "Released")
    released_remnants = _release_reserved_remnants(predecessor.name)

    return RevisionActivationContext(
        predecessor_name=predecessor.name,
        predecessor_plan=predecessor.approved_plan or None,
        revision_root=root_name,
        released_material_reservations=tuple(released_material),
        released_remnants=tuple(released_remnants),
    )


def finalize_revision_activation(
    order: Any,
    context: RevisionActivationContext | None,
    *,
    new_plan_name: str | None,
) -> dict[str, Any]:
    if context is None:
        if getattr(order, "revision_state", None) != RevisionState.CURRENT:
            frappe.db.set_value(
                "Door Cutting Order",
                order.name,
                "revision_state",
                RevisionState.CURRENT,
                update_modified=False,
            )
        return {"activated_revision": order.name, "replaced_revision": None}

    activated_on = now_datetime()
    actor = frappe.session.user

    if context.predecessor_plan:
        old_plan = frappe.get_doc("Cutting Plan", context.predecessor_plan)
        if old_plan.status == "Approved":
            old_plan.flags.allow_status_transition = True
            old_plan.status = "Superseded"
            old_plan.save(ignore_permissions=True)

    frappe.db.set_value(
        "Door Cutting Order",
        context.predecessor_name,
        {
            "revision_state": RevisionState.SUPERSEDED,
        },
        update_modified=True,
    )
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        {
            "revision_state": RevisionState.CURRENT,
            "revision_activated_by": actor,
            "revision_activated_on": activated_on,
        },
        update_modified=True,
    )

    predecessor = frappe.get_doc("Door Cutting Order", context.predecessor_name)
    predecessor.add_comment(
        "Comment",
        text=_("Revision {0} activated and replaced this revision.").format(order.name),
    )
    order.add_comment(
        "Comment",
        text=_("Activated as the current revision; replaced {0}.").format(
            context.predecessor_name
        ),
    )

    return {
        "activated_revision": order.name,
        "replaced_revision": context.predecessor_name,
        "revision_root": context.revision_root,
        "new_plan": new_plan_name,
        "released_material_reservations": list(
            context.released_material_reservations
        ),
        "released_remnants": list(context.released_remnants),
    }
