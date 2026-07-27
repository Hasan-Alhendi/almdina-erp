from __future__ import annotations


DRAFT_LIKE_STATUSES = frozenset({"Draft", "Pending Review", "Rejected"})
TERMINAL_STATUSES = frozenset({"Delivered", "Cancelled"})


class RevisionNotAllowed(ValueError):
    """Raised when an order cannot produce a controlled revision."""


def normalize_revision(value: int | str | None) -> int:
    try:
        revision = int(value or 1)
    except (TypeError, ValueError):
        revision = 1
    return max(1, revision)


def next_revision(value: int | str | None) -> int:
    return normalize_revision(value) + 1


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


def revision_root(*, order_name: str, current_root: str | None) -> str:
    root = str(current_root or "").strip()
    return root or str(order_name or "").strip()
