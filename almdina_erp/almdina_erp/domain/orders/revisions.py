from __future__ import annotations


DRAFT_LIKE_STATUSES = frozenset({"Draft", "Pending Review", "Rejected"})
TERMINAL_STATUSES = frozenset({"Delivered", "Cancelled"})
ACTIVATABLE_PREDECESSOR_STATUSES = frozenset({"Approved"})


class RevisionState:
    CURRENT = "Current"
    PENDING_ACTIVATION = "Pending Activation"
    SUPERSEDED = "Superseded"


REVISION_STATES = frozenset(
    value
    for name, value in vars(RevisionState).items()
    if name.isupper() and isinstance(value, str)
)


class RevisionNotAllowed(ValueError):
    """Raised when an order cannot produce a controlled revision."""


class RevisionActivationNotAllowed(ValueError):
    """Raised when a pending revision cannot safely replace its predecessor."""


def normalize_revision(value: int | str | None) -> int:
    try:
        revision = int(value or 1)
    except (TypeError, ValueError):
        revision = 1
    return max(1, revision)


def next_revision(value: int | str | None) -> int:
    return normalize_revision(value) + 1


def normalize_revision_state(value: str | None) -> str:
    state = str(value or "").strip()
    return state if state in REVISION_STATES else RevisionState.CURRENT


def initial_revision_state(revision_of: str | None) -> str:
    return RevisionState.PENDING_ACTIVATION if str(revision_of or "").strip() else RevisionState.CURRENT


def is_current_revision(state: str | None) -> bool:
    return normalize_revision_state(state) == RevisionState.CURRENT


def is_pending_activation(state: str | None) -> bool:
    return normalize_revision_state(state) == RevisionState.PENDING_ACTIVATION


def can_create_revision(status: str | None) -> bool:
    """Only immutable approved/production orders need a new editable document."""

    normalized = status or "Draft"
    return normalized not in DRAFT_LIKE_STATUSES and normalized not in TERMINAL_STATUSES


def assert_revision_allowed(status: str | None) -> None:
    normalized = status or "Draft"
    if normalized in DRAFT_LIKE_STATUSES:
        raise RevisionNotAllowed("Order is already editable and does not need a revision.")
    if normalized in TERMINAL_STATUSES:
        raise RevisionNotAllowed("Delivered or cancelled orders cannot create a revision.")


def assert_revision_dispatchable(
    state: str | None,
    *,
    competing_current_revision: bool = False,
) -> None:
    normalized = normalize_revision_state(state)
    if normalized == RevisionState.PENDING_ACTIVATION:
        raise RevisionActivationNotAllowed(
            "This revision is still pending activation and cannot be sent to production."
        )
    if normalized == RevisionState.SUPERSEDED:
        raise RevisionActivationNotAllowed(
            "This revision was superseded and cannot be sent to production."
        )
    if competing_current_revision:
        raise RevisionActivationNotAllowed(
            "More than one current revision exists in this order chain. Resolve the revision conflict before dispatch."
        )


def assert_revision_activation_allowed(
    *,
    revision_of: str | None,
    revision_state: str | None,
    predecessor_status: str | None,
    predecessor_state: str | None,
    predecessor_dispatched: bool,
    predecessor_has_open_stages: bool,
    predecessor_has_material_activity: bool,
    competing_current_revision: bool = False,
) -> None:
    """Validate the safe replacement boundary without consulting Frappe.

    A successor may replace only an approved predecessor that has not entered
    physical production. This keeps preparation of a revision possible while the
    old order is operating, but activation is blocked until the old workflow is
    explicitly resolved.
    """

    if not str(revision_of or "").strip():
        return
    if not is_pending_activation(revision_state):
        raise RevisionActivationNotAllowed(
            "Only a revision pending activation can replace the current revision."
        )
    if not is_current_revision(predecessor_state):
        raise RevisionActivationNotAllowed(
            "The predecessor is no longer the current revision."
        )
    if (predecessor_status or "") not in ACTIVATABLE_PREDECESSOR_STATUSES:
        raise RevisionActivationNotAllowed(
            "The previous revision must be approved and not yet dispatched before it can be replaced."
        )
    if predecessor_dispatched or predecessor_has_open_stages:
        raise RevisionActivationNotAllowed(
            "The previous revision has entered production. Cancel or complete its workflow before activating this revision."
        )
    if predecessor_has_material_activity:
        raise RevisionActivationNotAllowed(
            "The previous revision has material activity and cannot be replaced automatically."
        )
    if competing_current_revision:
        raise RevisionActivationNotAllowed(
            "Another current revision already exists in this revision chain."
        )


def revision_root(*, order_name: str, current_root: str | None) -> str:
    root = str(current_root or "").strip()
    return root or str(order_name or "").strip()
