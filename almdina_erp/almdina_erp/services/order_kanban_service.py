from __future__ import annotations

from typing import Any, NoReturn

import frappe
from frappe import _
from frappe.desk.doctype.kanban_board import kanban_board as frappe_kanban


_ORDER_DOCTYPE = "Door Cutting Order"
_STATUS_FIELD = "status"
_BLOCKED_MESSAGE = _(
    "حالة طلب القص للعرض فقط. نفّذ انتقالات الإنتاج من صالة الإنتاج وفق مسار الطلب."
)


def _board(board_name: str) -> Any:
    return frappe.get_doc("Kanban Board", board_name)


def _reject_status_mutation(board_name: str) -> None | NoReturn:
    board = _board(board_name)
    if (
        board.reference_doctype == _ORDER_DOCTYPE
        and board.field_name == _STATUS_FIELD
    ):
        frappe.throw(_BLOCKED_MESSAGE, frappe.ValidationError)


@frappe.whitelist()
def update_order(board_name: str, order: str) -> Any:
    _reject_status_mutation(board_name)
    return frappe_kanban.update_order(board_name, order)


@frappe.whitelist()
def update_order_for_single_card(
    board_name: str,
    docname: str,
    from_colname: str,
    to_colname: str,
    old_index: str | int,
    new_index: str | int,
) -> Any:
    _reject_status_mutation(board_name)
    return frappe_kanban.update_order_for_single_card(
        board_name,
        docname,
        from_colname,
        to_colname,
        old_index,
        new_index,
    )


@frappe.whitelist()
def add_card(board_name: str, docname: str, colname: str) -> Any:
    _reject_status_mutation(board_name)
    return frappe_kanban.add_card(board_name, docname, colname)


__all__ = ["add_card", "update_order", "update_order_for_single_card"]
