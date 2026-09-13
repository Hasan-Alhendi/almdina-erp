from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
)


ROOT = Path(__file__).resolve().parents[1]
INFRA_ROOT = ROOT / "almdina_erp" / "infrastructure" / "frappe"
STAGE_REPOSITORY_PATH = INFRA_ROOT / "production_stage_repository.py"
ORDER_TRACKING_PATH = INFRA_ROOT / "order_tracking_repository.py"
OFFCUT_SERVICE_PATH = ROOT / "almdina_erp" / "services" / "offcut_service.py"


class _InfrastructureHarness:
    def __init__(self, *, order_status: str = "Cutting") -> None:
        self.order_status = order_status
        self.set_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.stage_rows: list[Any] = []

    def load(self, path: Path, module_name: str):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = SimpleNamespace(
            set_value=lambda *args, **kwargs: self.set_calls.append((args, kwargs)),
            get_value=lambda doctype, name, fieldname, *args, **kwargs: (
                self.order_status
                if doctype == "Door Cutting Order" and fieldname == "status"
                else None
            ),
            exists=lambda *args, **kwargs: False,
            sql=lambda *args, **kwargs: [],
        )
        fake_frappe.get_all = lambda doctype, *args, **kwargs: (
            list(self.stage_rows) if doctype == "Production Stage" else []
        )
        fake_frappe.get_doc = lambda *args, **kwargs: None

        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.cint = lambda value: int(value or 0)
        fake_utils.now_datetime = lambda: "2026-09-13 10:00:00"
        fake_utils.time_diff_in_seconds = lambda end, start: 0

        replacements = {
            "frappe": fake_frappe,
            "frappe.utils": fake_utils,
        }
        previous = {name: sys.modules.get(name) for name in replacements}
        sys.modules.update(replacements)
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            for name, old in previous.items():
                if old is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = old


def test_zero_factory_offcut_price_is_an_explicit_invoice_line() -> None:
    document = build_customer_invoice_document(
        {
            "required_boards": 0,
            "offcut_factory_factory": True,
            "offcut_price_usd": 0,
        },
        [],
    )

    offcut_lines = [line for line in document["lines"] if line["type"] == "offcut"]
    assert offcut_lines == [
        {
            "type": "offcut",
            "description": "سعر الفضلة",
            "quantity": 1,
            "unit": "مجموعة",
            "rate_usd": 0.0,
            "amount_usd": 0.0,
            "note": "سعر إجمالي للمجموعة",
        }
    ]
    assert document["totals"] == [{"label": "الإجمالي النهائي", "value_usd": 0.0}]


def test_customer_source_context_still_has_no_offcut_invoice_line() -> None:
    document = build_customer_invoice_document(
        {
            "required_boards": 0,
            "offcut_factory_factory": False,
            "offcut_price_usd": 0,
        },
        [],
    )

    assert [line for line in document["lines"] if line["type"] == "offcut"] == []


def test_no_factory_work_cancellation_can_include_piece_specific_stages() -> None:
    harness = _InfrastructureHarness()
    harness.stage_rows = [
        SimpleNamespace(name="PST-ORDER", piece_label=None, stage_type="Cutting"),
        SimpleNamespace(name="PST-PIECE", piece_label="door:3", stage_type="CNC"),
    ]
    repository = harness.load(STAGE_REPOSITORY_PATH, "_almadina_178_stage_repository")

    cancelled = repository.cancel_active_order_stages(
        "DCO-1",
        include_piece_stages=True,
    )

    assert cancelled == ("PST-ORDER", "PST-PIECE")
    assert [call[0][1] for call in harness.set_calls] == ["PST-ORDER", "PST-PIECE"]
    assert all(call[0][2:4] == ("status", "Cancelled") for call in harness.set_calls)


def test_normal_redispatch_cancellation_keeps_piece_specific_stage_contract() -> None:
    harness = _InfrastructureHarness()
    harness.stage_rows = [
        SimpleNamespace(name="PST-ORDER", piece_label=None, stage_type="Cutting"),
        SimpleNamespace(name="PST-PIECE", piece_label="door:3", stage_type="CNC"),
    ]
    repository = harness.load(STAGE_REPOSITORY_PATH, "_almadina_178_stage_repository_legacy")

    cancelled = repository.cancel_active_order_stages("DCO-1")

    assert cancelled == ("PST-ORDER",)
    assert len(harness.set_calls) == 1
    assert harness.set_calls[0][0][1] == "PST-ORDER"


def test_clear_factory_tracking_returns_order_to_dispatchable_status() -> None:
    harness = _InfrastructureHarness(order_status="Cutting")
    repository = harness.load(ORDER_TRACKING_PATH, "_almadina_178_order_tracking")

    values = repository.clear_factory_tracking("DCO-1", fallback_status="Approved")

    assert values == {
        "production_path": None,
        "current_production_stage": None,
        "current_department": "",
        "current_assignee": "",
        "department_status": "",
        "status": "Approved",
    }
    assert harness.set_calls[0][0][2] == values


def test_clear_factory_tracking_preserves_terminal_order_status() -> None:
    harness = _InfrastructureHarness(order_status="Delivered")
    repository = harness.load(ORDER_TRACKING_PATH, "_almadina_178_order_tracking_terminal")

    values = repository.clear_factory_tracking("DCO-1", fallback_status="Approved")

    assert "status" not in values
    assert values["current_production_stage"] is None


def test_offcut_mutation_owns_immediate_production_reconciliation() -> None:
    source = OFFCUT_SERVICE_PATH.read_text(encoding="utf-8")
    function_source = source.split(
        "def _reconcile_factory_execution_projection", 1
    )[1].split("@frappe.whitelist", 1)[0]
    mutation_source = source.split("def set_offcut_execution_owner", 1)[1]

    assert "if execution.has_factory_work" in function_source
    assert "include_piece_stages=True" in function_source
    assert "clear_factory_tracking" in function_source
    assert "_reconcile_factory_execution_projection(" in mutation_source
