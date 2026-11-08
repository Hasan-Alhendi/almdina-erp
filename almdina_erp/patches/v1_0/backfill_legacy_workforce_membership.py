"""One-time historic workforce membership transition, after DocType sync."""

from almdina_erp.almdina_erp.infrastructure.frappe.workforce_membership import (
    backfill_legacy_workforce_membership,
    sync_workforce_membership_metadata,
)


def execute() -> None:
    # The column must exist before we read legacy membership sources.
    sync_workforce_membership_metadata()
    backfill_legacy_workforce_membership()


__all__ = ["execute"]
