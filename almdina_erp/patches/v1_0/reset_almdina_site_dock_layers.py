"""Clear incomplete site/user Dock layers so the shipped Almdina dock applies.

Frappe 16.60 resolves the desk rail from a standard app Dock plus optional site
and user arrangement layers. A pre-upgrade site layer that only named
``Almdina Reports`` hid the primary ``Almdina ERP`` shell even after the app
began shipping a complete standard dock. Deleting non-standard Almdina Dock
rows is idempotent and leaves Frappe to fall back to the exported dock.
"""

from __future__ import annotations

import frappe


APP = "almdina_erp"


def execute() -> None:
    if not frappe.db.exists("DocType", "Dock"):
        return

    names = frappe.get_all(
        "Dock",
        filters={"app": APP, "standard": 0},
        pluck="name",
    )
    for name in names:
        frappe.delete_doc("Dock", name, force=True, ignore_permissions=True)

    frappe.cache.delete_key("bootinfo")
