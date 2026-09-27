from __future__ import annotations

import json
from html import unescape
import re

import frappe


RETIRED_REPORTS = (
    "Factory Operations Summary",
    "Factory Order Analysis",
    "Production Stage Performance",
    "Board Usage Analysis",
    "Piece Size Usage Analysis",
    "Production Incidents and Replacements",
)
RETIRED_LABELS = RETIRED_REPORTS + (
    "ملخص عمليات المعمل",
    "تحليل طلبات القص",
    "تحليل استخدام الألواح",
    "تحليل قياسات الدرف",
    "أداء مراحل الإنتاج",
    "Operations Summary",
)
RETIRED_HEADERS = (
    "التقارير التشغيلية والتكلفة",
    "Factory Reports",
    "المتابعة والتقارير",
    "Validation Evidence",
)
RETIRED_CAPABILITY_KEYS = (
    "view_operational_reports",
    "view_financial_reports",
)
RETIRED_WORKSPACE = "Almdina Reports"
_TAG_RE = re.compile(r"<[^>]+>")


def execute() -> None:
    """Remove factory report documents and their permission keys.

    Costing, printing, and order data stay. The patch is idempotent: a second
    migrate finds the reports, workspace, and capability keys already gone.
    """

    _delete_reports()
    _delete_reports_workspace()
    _strip_workspace_report_entries()
    _strip_retired_capabilities()
    _delete_retired_permission_types()


def _delete_reports() -> None:
    if not frappe.db.table_exists("Report"):
        return
    for name in RETIRED_REPORTS:
        if frappe.db.exists("Report", name):
            frappe.delete_doc(
                "Report",
                name,
                force=True,
                ignore_permissions=True,
                delete_permanently=True,
            )


def _delete_reports_workspace() -> None:
    if not frappe.db.table_exists("Workspace"):
        return
    if frappe.db.exists("Workspace", RETIRED_WORKSPACE):
        frappe.delete_doc(
            "Workspace",
            RETIRED_WORKSPACE,
            force=True,
            ignore_permissions=True,
            delete_permanently=True,
        )


def _strip_workspace_report_entries() -> None:
    if frappe.db.table_exists("Workspace Link"):
        frappe.db.sql(
            """
            delete from `tabWorkspace Link`
            where link_to in %(names)s or label in %(labels)s
            """,
            {"names": RETIRED_REPORTS, "labels": RETIRED_LABELS},
        )
    if frappe.db.table_exists("Workspace Shortcut"):
        frappe.db.sql(
            """
            delete from `tabWorkspace Shortcut`
            where link_to in %(names)s or label in %(labels)s
            """,
            {"names": RETIRED_REPORTS, "labels": RETIRED_LABELS},
        )
    if not frappe.db.table_exists("Workspace"):
        return
    if not frappe.db.has_column("Workspace", "content"):
        return
    rows = frappe.db.sql(
        """
        select name, content
        from `tabWorkspace`
        where content is not null and content != ''
        """,
        as_dict=True,
    )
    for row in rows:
        cleaned = _without_report_blocks(row.content)
        if cleaned == row.content:
            continue
        frappe.db.set_value(
            "Workspace",
            row.name,
            "content",
            cleaned,
            update_modified=False,
        )


def _without_report_blocks(content: str) -> str:
    try:
        blocks = json.loads(content)
    except (TypeError, ValueError):
        return content
    if not isinstance(blocks, list):
        return content
    kept = [block for block in blocks if not _is_retired_block(block)]
    if len(kept) == len(blocks):
        return content
    return json.dumps(kept, ensure_ascii=False, separators=(",", ":"))


def _is_retired_block(block: object) -> bool:
    if not isinstance(block, dict):
        return False
    block_type = str(block.get("type") or "").strip().lower()
    data = block.get("data") if isinstance(block.get("data"), dict) else {}
    if block_type == "shortcut":
        label = str(data.get("shortcut_name") or data.get("label") or "").strip()
        return label in RETIRED_LABELS
    if block_type == "header":
        return _plain_text(data.get("text")) in RETIRED_HEADERS
    return False


def _plain_text(value: object) -> str:
    text = unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    return " ".join(text.split())


def _strip_retired_capabilities() -> None:
    if not frappe.db.table_exists("Almdina Role Capability State"):
        return
    if not frappe.db.has_column("Almdina Role Capability State", "capabilities_json"):
        return
    retired = set(RETIRED_CAPABILITY_KEYS)
    rows = frappe.db.sql(
        """
        select name, capabilities_json
        from `tabAlmdina Role Capability State`
        """,
        as_dict=True,
    )
    for row in rows:
        try:
            payload = json.loads(row.capabilities_json or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        cleaned = {key: value for key, value in payload.items() if key not in retired}
        if cleaned == payload:
            continue
        frappe.db.set_value(
            "Almdina Role Capability State",
            row.name,
            "capabilities_json",
            json.dumps(cleaned, ensure_ascii=False, sort_keys=True),
            update_modified=False,
        )


def _delete_retired_permission_types() -> None:
    if frappe.db.table_exists("Permission Type"):
        frappe.db.sql(
            """
            delete from `tabPermission Type`
            where name in %(names)s
            """,
            {"names": RETIRED_CAPABILITY_KEYS},
        )
    if not frappe.db.table_exists("Custom Field"):
        return
    frappe.db.sql(
        """
        delete from `tabCustom Field`
        where dt in ('DocPerm', 'Custom DocPerm')
          and fieldname in %(names)s
        """,
        {"names": RETIRED_CAPABILITY_KEYS},
    )
