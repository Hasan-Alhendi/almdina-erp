"""Remove the old ArtCAM catalog and operational files once.

The marker stops a later manual call from deleting records created after the
cleanup. Migrate also records this patch and does not run it again.
Customer orders, approved cutting plans, source DXF files, and the general
CNC machine settings on Almdina ERP Settings are not deleted.
"""

from __future__ import annotations

import frappe

_MARKER = "almdina_artcam_catalog_cleaned_v1"
_PRESET_LINKS = (
    "cnc_default_preset_cut_path",
    "cnc_default_preset_liner",
    "cnc_default_preset_rear_groove",
    "cnc_default_preset_handle_recess",
)
_CATALOG = (
    "CNC Operational File",
    "CNC Machining Profile",
    "CNC Tool Preset",
    "CNC Machine",
)


def execute() -> dict:
    if frappe.db.get_default(_MARKER) == "1":
        return {"skipped": True}

    summary = {
        "records": {},
        "exclusive_files_deleted": 0,
        "shared_files_detached": 0,
        "preset_links_cleared": 0,
    }
    for doctype in _CATALOG:
        summary["records"][doctype] = (
            frappe.db.count(doctype) if frappe.db.exists("DocType", doctype) else 0
        )

    # DDL commits the current transaction, so drop unused columns before the
    # record deletes. The deletes and the one-time marker then commit together.
    _drop_retired_catalog_columns()
    _clear_operational_files(summary)
    _clear_preset_links(summary)
    for doctype in _CATALOG[1:]:
        _delete_all(doctype)

    frappe.db.set_default(_MARKER, "1")
    frappe.logger("almdina_erp").info("ArtCAM catalog cleanup completed: %s", summary)
    return summary


def _clear_operational_files(summary: dict) -> None:
    if not frappe.db.exists("DocType", "CNC Operational File"):
        return
    names = frappe.get_all("CNC Operational File", pluck="name", limit_page_length=0)
    for name in names:
        _release_files(name, summary)
        frappe.delete_doc(
            "CNC Operational File",
            name,
            ignore_permissions=True,
            force=True,
            delete_permanently=True,
        )


def _release_files(operational_file: str, summary: dict) -> None:
    if not frappe.db.exists("DocType", "File"):
        return
    rows = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "CNC Operational File",
            "attached_to_name": operational_file,
        },
        fields=["name", "file_url"],
        limit_page_length=0,
    )
    for row in rows:
        file_url = str(row.file_url or "")
        shared = bool(
            file_url
            and frappe.db.count(
                "File",
                {"file_url": file_url, "name": ["!=", row.name]},
            )
        )
        if shared:
            frappe.db.set_value(
                "File",
                row.name,
                {"attached_to_doctype": None, "attached_to_name": None},
                update_modified=False,
            )
            summary["shared_files_detached"] += 1
            continue
        frappe.delete_doc("File", row.name, ignore_permissions=True, force=True, delete_permanently=True)
        summary["exclusive_files_deleted"] += 1


def _clear_preset_links(summary: dict) -> None:
    if not frappe.db.exists("DocType", "Almdina ERP Settings"):
        return
    # Singles live in tabSingles, so a table-column check is the wrong test.
    fields = {field.fieldname for field in frappe.get_meta("Almdina ERP Settings").fields}
    for fieldname in _PRESET_LINKS:
        if fieldname not in fields:
            continue
        if frappe.db.get_single_value("Almdina ERP Settings", fieldname):
            frappe.db.set_single_value("Almdina ERP Settings", fieldname, None)
            summary["preset_links_cleared"] += 1


def _drop_retired_catalog_columns() -> None:
    """Model sync does not drop business columns removed from a DocType."""
    retired = (
        ("CNC Tool Preset", "final_depth_mm"),
    )
    for doctype, column in retired:
        if frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, column):
            frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column `{column}`")


def _delete_all(doctype: str) -> None:
    if not frappe.db.exists("DocType", doctype):
        return
    for name in frappe.get_all(doctype, pluck="name", limit_page_length=0):
        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, delete_permanently=True)
