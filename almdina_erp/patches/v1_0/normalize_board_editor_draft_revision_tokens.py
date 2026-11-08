"""Rewrite legacy job-status labels in Board Editor Draft content revisions.

Old tokens ended with raw job status (idle/completed/queued/…). The live token
now uses a stable active-job bit (0|1). This patch rewrites only that last
segment when the label is recognized. Layout JSON and other fields are left
untouched. Safe to re-run.
"""

from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    normalize_content_revision_token,
)

DOCTYPE = "Board Editor Draft"
BATCH_SIZE = 200
_LEGACY_SUFFIXES = ("idle", "completed", "queued", "running", "enqueue")


def execute() -> None:
    if not frappe.db.table_exists(DOCTYPE):
        return
    if not frappe.db.has_column(DOCTYPE, "source_content_revision"):
        return

    while True:
        clauses = " or ".join(
            ["source_content_revision like %s"] * len(_LEGACY_SUFFIXES)
        )
        params = tuple(f"%|{label}" for label in _LEGACY_SUFFIXES) + (BATCH_SIZE,)
        rows = frappe.db.sql(
            f"""
            select name, source_content_revision
            from `tabBoard Editor Draft`
            where ({clauses})
            order by name
            limit %s
            """,
            params,
            as_dict=True,
        )
        if not rows:
            return

        for row in rows:
            stored = str(row.source_content_revision or "")
            normalized = normalize_content_revision_token(stored)
            if not normalized or normalized == stored:
                continue
            frappe.db.set_value(
                DOCTYPE,
                row.name,
                "source_content_revision",
                normalized,
                update_modified=False,
            )
        frappe.db.commit()
