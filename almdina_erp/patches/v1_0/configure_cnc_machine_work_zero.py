"""Set CNC Machine work zero and stops without copying a sheet offset.

Work zero becomes Bottom Left where it is empty, matching the previous
G54 frame. Stops become zero only when every saved operational-file offset
for that machine is zero, or when the machine has no saved file. Any
non-zero or conflicting history leaves the stops empty so the machine is
configured once. Operational-file rows and generated NC text are not
rewritten. Running the patch again does not change a machine that already
has stops.
"""

from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.domain.cnc.placement import legacy_machine_stops_remain_unset


def execute() -> None:
    if not frappe.db.table_exists("CNC Machine"):
        return
    if not frappe.db.has_column("CNC Machine", "work_zero_position"):
        return
    if not frappe.db.has_column("CNC Machine", "left_stop_cm"):
        return
    if not frappe.db.has_column("CNC Machine", "bottom_stop_cm"):
        return
    frappe.db.sql(
        """
        update `tabCNC Machine`
        set work_zero_position = 'Bottom Left'
        where ifnull(work_zero_position, '') = ''
        """
    )
    pending = frappe.db.sql(
        """
        select name
        from `tabCNC Machine`
        where left_stop_cm is null or bottom_stop_cm is null
        """,
        as_dict=True,
    )
    for row in pending:
        name = str(row.name)
        if legacy_machine_stops_remain_unset(_saved_offsets(name)):
            continue
        frappe.db.sql(
            """
            update `tabCNC Machine`
            set left_stop_cm = ifnull(left_stop_cm, 0),
                bottom_stop_cm = ifnull(bottom_stop_cm, 0)
            where name = %s
              and (left_stop_cm is null or bottom_stop_cm is null)
            """,
            (name,),
        )


def _saved_offsets(machine_name: str) -> list[tuple[object, object]]:
    if not frappe.db.table_exists("CNC Operational File"):
        return []
    if not frappe.db.has_column("CNC Operational File", "offset_left_cm"):
        return []
    if not frappe.db.has_column("CNC Operational File", "offset_bottom_cm"):
        return []
    rows = frappe.db.sql(
        """
        select offset_left_cm, offset_bottom_cm
        from `tabCNC Operational File`
        where cnc_machine = %s
        """,
        (machine_name,),
        as_dict=True,
    )
    return [(row.offset_left_cm, row.offset_bottom_cm) for row in rows]
