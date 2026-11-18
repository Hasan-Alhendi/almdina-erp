"""Map retired CNC operational-file statuses onto the settings statuses.

A persisted row is saved sheet settings. Machines, tool presets, profiles,
vector associations, toolpath snapshots, perimeter settings, operation order,
path directions, and sheet offsets are not modified.

Legacy NC attachment fields stay in place. Their removal is a separate dry-run
plan in ``application.cnc.legacy_nc_cleanup`` and is not executed here.
"""

from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.application.cnc.legacy_nc_cleanup import plan_legacy_nc_cleanup

LEGACY_STATUS_TO_SETTINGS_SAVED = {
    "Not Generated": "Settings Saved",
    "Generated": "Settings Saved",
    "Needs Regeneration": "Settings Saved",
}


def mapped_operational_status(status: str) -> str | None:
    """Return the replacement status, or None when the current value can stay."""

    return LEGACY_STATUS_TO_SETTINGS_SAVED.get(str(status or "").strip())


def execute() -> None:
    if not frappe.db.table_exists("CNC Operational File"):
        return
    if not frappe.db.has_column("CNC Operational File", "status"):
        return
    for old, new in LEGACY_STATUS_TO_SETTINGS_SAVED.items():
        frappe.db.sql(
            """
            update `tabCNC Operational File`
            set status = %s
            where status = %s
            """,
            (new, old),
        )


def preview_legacy_nc_cleanup() -> dict:
    """Read the legacy NC attachment scope. This does not delete or clear anything."""

    if not frappe.db.table_exists("CNC Operational File"):
        return plan_legacy_nc_cleanup([], [])
    fields = ["name", "generated_file", "generated_by", "generated_on", "generation_snapshot_json"]
    available = [field for field in fields if frappe.db.has_column("CNC Operational File", field)]
    operational_files = frappe.get_all(
        "CNC Operational File",
        fields=available,
        limit_page_length=0,
        ignore_permissions=True,
    )
    file_fields = ["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name"]
    files = []
    if frappe.db.table_exists("File"):
        files = frappe.get_all(
            "File",
            filters={"attached_to_doctype": "CNC Operational File"},
            fields=file_fields,
            limit_page_length=0,
            ignore_permissions=True,
        )
        urls = []
        for row in operational_files:
            generated = str(row.get("generated_file") or "").strip()
            if generated:
                urls.append(generated)
        if urls:
            referenced = frappe.get_all(
                "File",
                filters={"file_url": ["in", urls]},
                fields=file_fields,
                limit_page_length=0,
                ignore_permissions=True,
            )
            seen = {str(row.get("name") or "") for row in files}
            for row in referenced:
                if str(row.get("name") or "") not in seen:
                    files.append(row)
    plan = plan_legacy_nc_cleanup(operational_files, files)
    plan["deletes_executed"] = 0
    return plan
