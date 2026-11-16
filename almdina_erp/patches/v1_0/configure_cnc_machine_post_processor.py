"""Give existing CNC machines the only supported post processor.

IMA-WH is the only registered dialect. Machines with an empty processor
receive that id. A machine that already has a value is left unchanged.
Operational-file rows and generated NC text are not rewritten. Running the
patch again does not change a machine that already has a processor.
"""

from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.cnc.post_processors import IMA_WH_ID


def execute() -> None:
    if not frappe.db.table_exists("CNC Machine"):
        return
    if not frappe.db.has_column("CNC Machine", "post_processor"):
        return
    frappe.db.sql(
        """
        update `tabCNC Machine`
        set post_processor = %(processor)s
        where ifnull(post_processor, '') = ''
        """,
        {"processor": IMA_WH_ID},
    )
