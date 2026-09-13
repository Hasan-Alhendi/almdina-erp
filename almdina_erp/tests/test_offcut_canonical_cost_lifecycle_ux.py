from __future__ import annotations

import copy
from types import SimpleNamespace

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
)
from almdina_erp.almdina_erp.services import offcut_service


def _snapshot(*resource_kinds: str) -> dict:
    return {
        "sheets": [
            {
                "sheet_no": index,
                "resource_kind": kind,
                "pieces": [
                    {
                        "piece_instance_id": f"piece:{index}",
                        "resource_kind": kind,
                    }
                ],
            }
            for index, kind in enumerate(resource_kinds, start=1)
        ]
    }


def test_required_boards_reconciles_from_physical_sources_without_mutating_snapshot(monkeypatch) -> None:
    snapshot = _snapshot("FULL_BOARD", "FULL_BOARD", "OFFCUT")
    original = copy.deepcopy(snapshot)
    plan = SimpleNamespace(name="CP-OFFCUT-COST", required_boards=3)
    writes: list[tuple[tuple, dict]] = []

    monkeypatch.setattr(
        offcut_service.frappe.db,
        "set_value",
        lambda *args, **kwargs: writes.append((args, kwargs)),
    )

    required = offcut_service._reconcile_required_boards(plan, snapshot)

    assert required == 2
    assert plan.required_boards == 2
    assert snapshot == original
    assert writes == [
        (
            ("Cutting Plan", plan.name, "required_boards", 2),
            {"update_modified": False},
        )
    ]


def test_all_offcut_reconciles_to_zero_new_board_cost_basis(monkeypatch) -> None:
    plan = SimpleNamespace(name="CP-ALL-OFFCUT", required_boards=4)
    monkeypatch.setattr(offcut_service.frappe.db, "set_value", lambda *args, **kwargs: None)

    required = offcut_service._reconcile_required_boards(
        plan,
        _snapshot("OFFCUT", "OFFCUT"),
    )

    assert required == 0
    assert plan.required_boards == 0


def test_full_board_only_reconciliation_is_unchanged(monkeypatch) -> None:
    plan = SimpleNamespace(name="CP-FULL", required_boards=2)
    monkeypatch.setattr(offcut_service.frappe.db, "set_value", lambda *args, **kwargs: None)

    required = offcut_service._reconcile_required_boards(
        plan,
        _snapshot("FULL_BOARD", "FULL_BOARD"),
    )

    assert required == 2
    assert plan.required_boards == 2


def test_required_regression_invoice_total_is_exactly_54() -> None:
    order = {
        "required_boards": 2,
        "board_rate_usd": 22,
        "cutting_cost_per_board_usd": 2.5,
        "mdf_cost_usd": 44,
        "cutting_cost_usd": 5,
        "offcut_factory_factory": False,
        "offcut_price_usd": 0,
    }
    pieces = [
        {
            "piece_type": "Clipped Corner",
            "qty": 2,
            "factory_execution_qty": 2,
            "clipped_corner_edge_price_usd": 2,
        },
        {
            "piece_type": "L-Shaped Corner",
            "qty": 2,
            "factory_execution_qty": 1,
            "clipped_corner_edge_price_usd": 1,
        },
    ]

    document = build_customer_invoice_document(order, pieces)
    lines = document["lines"]
    amounts = {line["type"]: [] for line in lines}
    for line in lines:
        amounts.setdefault(line["type"], []).append(line["amount_usd"])

    assert amounts["material"] == [44.0]
    assert amounts["cutting"] == [5.0]
    assert amounts["cut_corner"] == [4.0, 1.0]
    assert pieces[1]["qty"] == 2
    assert pieces[1]["factory_execution_qty"] == 1
    assert document["totals"] == [{"label": "الإجمالي النهائي", "value_usd": 54.0}]
