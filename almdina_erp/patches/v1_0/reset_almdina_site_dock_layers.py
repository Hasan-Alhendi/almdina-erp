"""Clear incomplete site/user Dock layers so the shipped Almdina dock applies.

Frappe 16.60 resolves the desk rail from a standard app Dock plus optional site
and user arrangement layers. A pre-upgrade site layer that only named
``Almdina Reports`` hid the primary ``Almdina ERP`` shell even after the app
began shipping a complete standard dock.

Only incomplete non-standard Almdina Dock rows are deleted. Healthy site/user
arrangements that still expose the primary shell are preserved.
"""

from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.native_app_navigation import (
    list_incomplete_almdina_dock_layers,
)


def execute() -> None:
    names = list_incomplete_almdina_dock_layers()
    for name in names:
        frappe.delete_doc("Dock", name, force=True, ignore_permissions=True)

    if names:
        frappe.cache.delete_key("bootinfo")
