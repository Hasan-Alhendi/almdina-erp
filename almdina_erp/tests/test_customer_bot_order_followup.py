"""In-memory contracts for customer-bot order reading.

Database filtering and page size are covered by the integration module.
These tests do not open a site or a network connection.
"""

from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

from almdina_erp.almdina_erp.application.customer_bot.read_customer_orders import (
    list_current_customer_orders,
    select_customer_order_by_name,
)
from almdina_erp.almdina_erp.application.customer_bot.order_followup_ports import (
    CustomerOrderHeader,
    ProductionStageFacts,
)
from almdina_erp.almdina_erp.application.shop_floor.order_list_query import (
    _effective_order_status,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import IdentityCode
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    CurrentOrderList,
    CurrentOrderListOutcome,
    CustomerOrderSummary,
    OrderSelection,
    OrderSelectionOutcome,
    OrderStatusFacts,
    PublicOrderStatus,
    classify_public_order_status,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import (
    ProductionRoute,
    RoutingStage,
)
from almdina_erp.almdina_erp.domain.orders.revisions import RevisionState

ROOT = Path(__file__).resolve().parents[1]
PHONE = "0988100101"
NORMALIZED = "+963988100101"
CUSTOMER = "CUST-A"
OTHER = "CUST-B"


def _header(
    name: str,
    *,
    customer: str = CUSTOMER,
    order_date: str | None = "2026-10-01",
    stored_status: str = "Draft",
    revision_state: str = RevisionState.CURRENT,
    production_path: str = "",
    current_stage_name: str = "",
) -> CustomerOrderHeader:
    return CustomerOrderHeader(
        name=name,
        customer_id=customer,
        order_date=order_date,
        stored_status=stored_status,
        revision_state=revision_state,
        production_path=production_path,
        current_stage_name=current_stage_name,
    )


class _Directory:
    def __init__(self) -> None:
        self.matches: dict[str, tuple[str, ...]] = {NORMALIZED: (CUSTOMER,)}
        self.lookups: list[str] = []

    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        self.lookups.append(normalized_phone)
        return self.matches.get(normalized_phone, ())

    def customer_exists(self, customer_id: str) -> bool:
        return customer_id == CUSTOMER


class _Headers:
    def __init__(self, rows: tuple[CustomerOrderHeader, ...] = ()) -> None:
        self.rows = rows
        self.list_customers: list[str] = []
        self.exact_names: list[str] = []

    def list_current_headers(self, customer_id: str) -> tuple[CustomerOrderHeader, ...]:
        self.list_customers.append(customer_id)
        return tuple(row for row in self.rows if row.customer_id == customer_id)

    def get_header_by_exact_name(self, order_name: str) -> CustomerOrderHeader | None:
        self.exact_names.append(order_name)
        for row in self.rows:
            if row.name == order_name:
                return row
        return None


class _Stages:
    def __init__(self, rows: dict[str, ProductionStageFacts] | None = None) -> None:
        self.rows = rows or {}
        self.calls = 0

    def stages_for_orders(self, pointers: tuple[tuple[str, str], ...]) -> dict[str, ProductionStageFacts]:
        self.calls += 1
        return {
            stage_name: self.rows[stage_name]
            for _order_name, stage_name in pointers
            if stage_name in self.rows
        }


class _Routes:
    def __init__(self, flags: dict[tuple[str, str], bool | None] | None = None) -> None:
        self.flags = flags or {}
        self.calls = 0

    def terminal_by_path_and_stage(
        self, keys: tuple[tuple[str, str], ...]
    ) -> dict[tuple[str, str], bool | None]:
        self.calls += 1
        return {key: self.flags.get(key) for key in keys}


def _route() -> ProductionRoute:
    return ProductionRoute(
        name="route",
        label="Route",
        stages=(
            RoutingStage(1, "middle", "Middle", "Role"),
            RoutingStage(2, "last", "Last", "Role"),
        ),
    )


class CustomerBotOrderFollowupTests(unittest.TestCase):
    def test_no_current_orders_is_distinct_from_an_unknown_phone(self) -> None:
        directory = _Directory()
        listed = list_current_customer_orders(directory, _Headers(), _Stages(), _Routes(), PHONE)
        self.assertEqual(listed.outcome, CurrentOrderListOutcome.NONE)
        self.assertEqual(listed.orders, ())
        unknown = list_current_customer_orders(
            _Directory(), _Headers(), _Stages(), _Routes(), "0988100199"
        )
        self.assertEqual(unknown.outcome, CurrentOrderListOutcome.IDENTITY_UNAVAILABLE)
        self.assertEqual(unknown.identity_code, IdentityCode.UNKNOWN)
        self.assertNotEqual(listed.outcome, unknown.outcome)

    def test_one_order_and_many_orders_keep_separate_outcomes(self) -> None:
        one = self._list((_header("DCO-2026-00001"),))
        self.assertEqual(one.outcome, CurrentOrderListOutcome.ONE)
        self.assertEqual(one.orders[0].order_name, "DCO-2026-00001")
        self.assertEqual(one.orders[0].public_status, PublicOrderStatus.AWAITING_START)
        many = self._list(tuple(_header(f"DCO-2026-{index:05d}") for index in range(1, 26)))
        self.assertEqual(many.outcome, CurrentOrderListOutcome.MANY)
        self.assertEqual(len(many.orders), 25)

    def test_list_omits_delivered_cancelled_and_non_current_copies(self) -> None:
        listed = self._list(
            (
                _header("DCO-DRAFT"),
                _header("DCO-DELIVERED", stored_status="Delivered"),
                _header("DCO-CANCELLED", stored_status="Cancelled"),
                _header("DCO-OLD", revision_state=RevisionState.SUPERSEDED),
                _header("DCO-PENDING", revision_state=RevisionState.PENDING_ACTIVATION),
                _header("DCO-FOREIGN", customer=OTHER),
            )
        )
        self.assertEqual(tuple(item.order_name for item in listed.orders), ("DCO-DRAFT",))

    def test_same_date_orders_sort_by_name_descending_without_dropping_rows(self) -> None:
        listed = self._list(
            (
                _header("DCO-2026-00002", order_date="2026-10-01"),
                _header("DCO-2026-00001", order_date="2026-10-02"),
                _header("DCO-2026-00003", order_date="2026-10-01"),
                _header("DCO-UNDATED", order_date=None),
            )
        )
        self.assertEqual(
            tuple(item.order_name for item in listed.orders),
            ("DCO-2026-00001", "DCO-2026-00003", "DCO-2026-00002", "DCO-UNDATED"),
        )

    def test_draft_awaits_start_and_a_middle_stage_is_not_ready(self) -> None:
        self.assertEqual(
            self._list((_header("DCO-DRAFT"),)).orders[0].public_status,
            PublicOrderStatus.AWAITING_START,
        )
        active = self._list(
            (_header("DCO-MID", production_path="route", current_stage_name="ST-MID"),),
            stages={
                "ST-MID": ProductionStageFacts("ST-MID", "Completed", "middle"),
            },
            routes={("route", "middle"): False},
        )
        self.assertEqual(active.orders[0].public_status, PublicOrderStatus.IN_PROGRESS)
        pending = self._list(
            (_header("DCO-RUN", production_path="route", current_stage_name="ST-RUN"),),
            stages={"ST-RUN": ProductionStageFacts("ST-RUN", "In Progress", "middle")},
            routes={("route", "middle"): False},
        )
        self.assertEqual(pending.orders[0].public_status, PublicOrderStatus.IN_PROGRESS)

    def test_completed_last_stage_is_ready_and_unknown_route_is_unsupported(self) -> None:
        ready = self._list(
            (_header("DCO-READY", production_path="route", current_stage_name="ST-LAST"),),
            stages={"ST-LAST": ProductionStageFacts("ST-LAST", "Completed", "last")},
            routes={("route", "last"): True},
        )
        self.assertEqual(ready.orders[0].public_status, PublicOrderStatus.READY_FOR_PICKUP)
        unsupported = self._list(
            (_header("DCO-UNKNOWN", production_path="missing", current_stage_name="ST-LAST"),),
            stages={"ST-LAST": ProductionStageFacts("ST-LAST", "Completed", "last")},
            routes={("missing", "last"): None},
        )
        self.assertEqual(unsupported.orders[0].public_status, PublicOrderStatus.UNSUPPORTED)
        stored_ready = classify_public_order_status(
            OrderStatusFacts("Ready for Delivery", "", "", "", "", "", None)
        )
        self.assertEqual(stored_ready, PublicOrderStatus.READY_FOR_PICKUP)
        contradicted = classify_public_order_status(
            OrderStatusFacts(
                "Ready for Delivery",
                "route",
                "ST-MID",
                "ST-MID",
                "Completed",
                "middle",
                False,
            )
        )
        self.assertEqual(contradicted, PublicOrderStatus.UNSUPPORTED)

    def test_delivered_selection_is_accepted_when_it_is_absent_from_the_list(self) -> None:
        rows = (
            _header("DCO-OPEN"),
            _header("DCO-DONE", stored_status="Delivered", order_date="2026-09-01"),
        )
        listed = self._list(rows)
        self.assertEqual(tuple(item.order_name for item in listed.orders), ("DCO-OPEN",))
        selected = self._select(rows, "DCO-DONE")
        self.assertEqual(selected.outcome, OrderSelectionOutcome.SELECTED)
        self.assertEqual(selected.public_status, PublicOrderStatus.DELIVERED)
        self.assertEqual(selected.order_name, "DCO-DONE")

    def test_cancelled_owned_order_returns_cancellation_only(self) -> None:
        selected = self._select(
            (_header("DCO-STOP", stored_status="Cancelled", production_path="route"),),
            "DCO-STOP",
        )
        self.assertEqual(selected.outcome, OrderSelectionOutcome.CANCELLED)
        self.assertEqual(selected.public_status, PublicOrderStatus.CANCELLED)
        self.assertEqual(
            {item.name for item in fields(selected)},
            {"outcome", "identity_code", "order_name", "order_date", "public_status"},
        )

    def test_missing_and_foreign_orders_are_the_same_external_result(self) -> None:
        rows = (_header("DCO-FOREIGN", customer=OTHER, stored_status="Delivered"),)
        missing = self._select(rows, "DCO-ABSENT")
        foreign = self._select(rows, "DCO-FOREIGN")
        self.assertEqual(missing, foreign)
        self.assertEqual(missing.outcome, OrderSelectionOutcome.NOT_FOUND)
        self.assertIsNone(missing.order_name)
        self.assertIsNone(missing.public_status)

    def test_partial_and_wildcard_names_do_not_match(self) -> None:
        headers = _Headers((_header("DCO-2026-00010"),))
        partial = select_customer_order_by_name(
            _Directory(), headers, _Stages(), _Routes(), PHONE, "DCO-2026-0001"
        )
        self.assertEqual(partial.outcome, OrderSelectionOutcome.NOT_FOUND)
        self.assertEqual(headers.exact_names, ["DCO-2026-0001"])
        wildcard_headers = _Headers((_header("DCO-2026-00010"),))
        wildcard = select_customer_order_by_name(
            _Directory(), wildcard_headers, _Stages(), _Routes(), PHONE, "DCO%"
        )
        self.assertEqual(wildcard, partial)
        self.assertEqual(wildcard_headers.exact_names, [])

    def test_non_current_owned_copy_is_not_replaced_by_another_order(self) -> None:
        selected = self._select(
            (
                _header("DCO-OLD", revision_state=RevisionState.SUPERSEDED),
                _header("DCO-NEW"),
            ),
            "DCO-OLD",
        )
        self.assertEqual(selected.outcome, OrderSelectionOutcome.NOT_CURRENT)
        self.assertEqual(selected.order_name, "DCO-OLD")
        self.assertIsNone(selected.public_status)
        self.assertNotIn("DCO-NEW", str(selected))
        pending = self._select(
            (_header("DCO-WAIT", revision_state=RevisionState.PENDING_ACTIVATION),),
            "DCO-WAIT",
        )
        self.assertEqual(pending.outcome, OrderSelectionOutcome.NOT_CURRENT)

    def test_a_changed_primary_phone_is_resolved_again(self) -> None:
        directory = _Directory()
        headers = _Headers((_header("DCO-A"), _header("DCO-B", customer=OTHER)))
        first = list_current_customer_orders(directory, headers, _Stages(), _Routes(), PHONE)
        self.assertEqual(first.orders[0].order_name, "DCO-A")
        directory.matches = {NORMALIZED: (OTHER,)}
        second = list_current_customer_orders(directory, headers, _Stages(), _Routes(), PHONE)
        self.assertEqual(second.orders[0].order_name, "DCO-B")
        self.assertEqual(len(directory.lookups), 2)

    def test_an_additional_grant_does_not_authorize_a_read(self) -> None:
        directory = _Directory()
        directory.matches = {}
        headers = _Headers((_header("DCO-A"),))
        listed = list_current_customer_orders(
            directory, headers, _Stages(), _Routes(), "0988100188"
        )
        self.assertEqual(listed.outcome, CurrentOrderListOutcome.IDENTITY_UNAVAILABLE)
        self.assertEqual(headers.list_customers, [])

    def test_results_have_no_financial_note_or_staff_fields(self) -> None:
        allowed = {
            CurrentOrderList: {"outcome", "identity_code", "orders"},
            CustomerOrderSummary: {"order_name", "order_date", "public_status"},
            OrderSelection: {
                "outcome",
                "identity_code",
                "order_name",
                "order_date",
                "public_status",
            },
            CustomerOrderHeader: {
                "name",
                "customer_id",
                "order_date",
                "stored_status",
                "revision_state",
                "production_path",
                "current_stage_name",
            },
            ProductionStageFacts: {"name", "status", "stage_type"},
        }
        for model, names in allowed.items():
            self.assertEqual({item.name for item in fields(model)}, names)
        rendered = str(self._list((_header("DCO-A"),)))
        for forbidden in ("cost", "price", "quote", "notes", "assigned", "dxf", "file"):
            self.assertNotIn(forbidden, rendered)

    def test_stage_and_route_lookups_are_batched_once(self) -> None:
        stages = _Stages(
            {
                "ST-1": ProductionStageFacts("ST-1", "In Progress", "middle"),
                "ST-2": ProductionStageFacts("ST-2", "Pending", "middle"),
            }
        )
        routes = _Routes({("route", "middle"): False})
        self._list(
            (
                _header("DCO-1", production_path="route", current_stage_name="ST-1"),
                _header("DCO-2", production_path="route", current_stage_name="ST-2"),
            ),
            stages=stages,
            routes=routes,
        )
        self.assertEqual(stages.calls, 1)
        self.assertEqual(routes.calls, 1)

    def test_use_cases_do_not_accept_a_customer_or_ownership_argument(self) -> None:
        for function in (list_current_customer_orders, select_customer_order_by_name):
            parameters = set(inspect.signature(function).parameters)
            self.assertIn("phone", parameters)
            self.assertNotIn("customer_id", parameters)
            self.assertNotIn("allowed", parameters)

    def test_read_modules_do_not_send_optimize_or_expose_an_endpoint(self) -> None:
        reader = (
            ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "customer_bot_order_reader.py"
        ).read_text(encoding="utf-8")
        gateway = (
            ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "customer_bot_order_gateway.py"
        ).read_text(encoding="utf-8")
        application = (
            ROOT / "almdina_erp" / "application" / "customer_bot" / "read_customer_orders.py"
        ).read_text(encoding="utf-8")
        domain = (
            ROOT / "almdina_erp" / "domain" / "customer_bot" / "order_followup.py"
        ).read_text(encoding="utf-8")
        for source in (reader, gateway, application):
            self.assertNotIn("frappe.whitelist", source)
            self.assertNotIn("optimizer", source)
            self.assertNotIn("whatsapp", source)
        for forbidden in ("set_value", "insert(", "save(", "LIKE", "assigned_to", "order_notes"):
            self.assertNotIn(forbidden, reader)
        self.assertNotIn("Administrator", application)
        self.assertNotRegex(domain, r"[\u0600-\u06FF]")
        ast.parse(reader)
        ast.parse(application)

    def test_shop_floor_ready_rule_stays_on_the_terminal_stage(self) -> None:
        route = _route()
        last_order = SimpleNamespace(
            status="In Progress",
            production_path="route",
            current_production_stage="ST-LAST",
        )
        last_stage = SimpleNamespace(name="ST-LAST", status="Completed", stage_type="last")
        self.assertEqual(
            _effective_order_status(last_order, last_stage, {"route": route}),
            "Ready for Delivery",
        )
        self.assertIsNone(route.next_stage("last"))
        middle_order = SimpleNamespace(
            status="Drawing",
            production_path="route",
            current_production_stage="ST-MID",
        )
        middle_stage = SimpleNamespace(name="ST-MID", status="Completed", stage_type="middle")
        self.assertEqual(
            _effective_order_status(middle_order, middle_stage, {"route": route}),
            "Drawing",
        )
        self.assertIsNotNone(route.next_stage("middle"))
        facts = OrderStatusFacts(
            stored_status="Drawing",
            production_path="route",
            current_stage_name="ST-MID",
            stage_row_name="ST-MID",
            stage_status="Completed",
            stage_type="middle",
            route_terminal=False,
        )
        self.assertEqual(classify_public_order_status(facts), PublicOrderStatus.IN_PROGRESS)

    def _list(self, rows, stages=None, routes=None):
        return list_current_customer_orders(
            _Directory(),
            _Headers(tuple(rows)),
            stages if isinstance(stages, _Stages) else _Stages(stages),
            routes if isinstance(routes, _Routes) else _Routes(routes),
            PHONE,
        )

    def _select(self, rows, order_name: str) -> OrderSelection:
        return select_customer_order_by_name(
            _Directory(),
            _Headers(tuple(rows)),
            _Stages(),
            _Routes(),
            PHONE,
            order_name,
        )


if __name__ == "__main__":
    unittest.main()
