"""Install the customer-bot access permission type without granting it.

Repeated migrate only repairs the Permission Type column. Existing role
grants are left unchanged, and no historical phone becomes an access row.
"""

from __future__ import annotations


def execute() -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
        sync_permission_types,
    )

    sync_permission_types()
