"""Behavioral tests for the customer-bot conversation engine.

Order rows sit in a memory repository. Listing and selection go through the
real customer-order use cases. Nothing is sent and no site is opened.
"""

from __future__ import annotations

import inspect
import itertools
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from almdina_erp.almdina_erp.application.customer_bot.approved_plan_service import (
    CustomerBotApprovedPlanService,
    CustomerBotApprovedPlanSnapshot,
)
from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    CustomerBotServiceRouter,
    CustomerServiceRequest,
    CustomerServiceResult,
    UnavailableCustomerBotServices,
)
from almdina_erp.almdina_erp.application.customer_bot.handle_conversation import (
    handle_customer_conversation,
)
from almdina_erp.almdina_erp.application.customer_bot.order_followup_ports import (
    CustomerOrderHeader,
    ProductionStageFacts,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotMessageKey,
    BotService,
    ConversationContext,
    ConversationPhase,
    ServiceResultCode,
    conversation_state_from_payload,
)
from almdina_erp.almdina_erp.domain.customer_bot.documents import CustomerBotDocument
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import PublicOrderStatus
from almdina_erp.almdina_erp.domain.orders.revisions import RevisionState
from almdina_erp.tests.customer_bot_conversation_texts import render_turn

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
TTL = timedelta(minutes=30)
PHONE = "+963988100101"
CUSTOMER = "CUST-A"
OTHER = "CUST-B"
ROOT = Path(__file__).resolve().parents[1]
_EVENT_IDS = itertools.count()


class _Directory:
    def __init__(self, matches: dict[str, tuple[str, ...]] | None = None) -> None:
        self.matches = {PHONE: (CUSTOMER,)} if matches is None else matches
        self.calls = 0

    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        self.calls += 1
        return self.matches.get(normalized_phone, ())

    def customer_exists(self, customer_id: str) -> bool:
        return False


class _Orders:
    def __init__(self, rows: tuple[CustomerOrderHeader, ...] = ()) -> None:
        self.rows = rows
        self.list_calls = 0
        self.exact_names: list[str] = []

    def list_current_headers(self, customer_id: str) -> tuple[CustomerOrderHeader, ...]:
        self.list_calls += 1
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

    def stages_for_orders(self, pointers: tuple[tuple[str, str], ...]) -> dict[str, ProductionStageFacts]:
        return {
            stage_name: self.rows[stage_name]
            for _order_name, stage_name in pointers
            if stage_name in self.rows
        }


class _Routes:
    def __init__(self, flags: dict[tuple[str, str], bool | None] | None = None) -> None:
        self.flags = flags or {}

    def terminal_by_path_and_stage(
        self, keys: tuple[tuple[str, str], ...]
    ) -> dict[tuple[str, str], bool | None]:
        return {key: self.flags.get(key) for key in keys}


class _Services:
    def __init__(self, result: CustomerServiceResult | None = None) -> None:
        self.requests: list[CustomerServiceRequest] = []
        self.result = result or CustomerServiceResult(ServiceResultCode.UNAVAILABLE)

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        self.requests.append(request)
        return self.result


class _Exploding:
    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        raise AssertionError("identity was called")

    def customer_exists(self, customer_id: str) -> bool:
        raise AssertionError("identity was called")

    def list_current_headers(self, customer_id: str) -> tuple[CustomerOrderHeader, ...]:
        raise AssertionError("orders were listed")

    def get_header_by_exact_name(self, order_name: str) -> CustomerOrderHeader | None:
        raise AssertionError("an order was selected")

    def stages_for_orders(self, pointers: tuple[tuple[str, str], ...]) -> dict[str, ProductionStageFacts]:
        raise AssertionError("stages were read")

    def terminal_by_path_and_stage(self, keys: tuple[tuple[str, str], ...]) -> dict[tuple[str, str], bool | None]:
        raise AssertionError("routes were read")

    def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
        raise AssertionError("a service was executed")


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


def _inbound(
    text: str,
    *,
    phone: str | None = PHONE,
    sender: str = "sender-a",
    connection: str = "conn-a",
    conversation: str = "chat-a",
    own: bool = False,
    group: bool = False,
    kind: InboundMessageKind = InboundMessageKind.TEXT,
    when: datetime = NOW,
):
    return build_inbound_customer_message(
        connection_ref=connection,
        provider_event_id=f"evt-{next(_EVENT_IDS)}",
        conversation_id=conversation,
        sender_id=sender,
        occurred_at=when,
        kind=kind,
        text=text,
        from_own_account=own,
        is_group=group,
        trusted_normalized_phone=phone,
    )


def _context(when: datetime = NOW, *, enabled: bool = True) -> ConversationContext:
    return ConversationContext(enabled=enabled, now=when, session_ttl=TTL)


def _run(
    text: str,
    state,
    orders: _Orders,
    directory: _Directory | None = None,
    services: _Services | None = None,
    **inbound,
):
    directory = directory or _Directory()
    services = services or _Services()
    when = inbound.get("when", NOW)
    turn = handle_customer_conversation(
        _inbound(text, **inbound),
        state,
        _context(when),
        directory,
        orders,
        _Stages(),
        _Routes(),
        services,
    )
    return turn, directory, services


class CustomerBotConversationTests(unittest.TestCase):
    def test_first_message_is_welcome_and_menu_without_reading_orders(self) -> None:
        orders = _Orders((_header("DCO-2026-00021"),))
        turn, _directory, services = _run("1", None, orders)
        self.assertEqual(
            tuple(item.key for item in turn.messages),
            (BotMessageKey.WELCOME, BotMessageKey.MAIN_MENU),
        )
        self.assertEqual(turn.state.phase, ConversationPhase.MAIN_MENU)
        self.assertIsNone(turn.state.service_id)
        self.assertEqual(orders.list_calls, 0)
        self.assertEqual(services.requests, [])

    def test_unknown_and_conflict_share_one_public_result(self) -> None:
        unknown, _directory, _services = _run(
            "مرحبا", None, _Orders(), directory=_Directory({})
        )
        conflict, _directory, _services = _run(
            "مرحبا",
            None,
            _Orders((_header("DCO-1"),)),
            directory=_Directory({PHONE: (CUSTOMER, OTHER)}),
        )
        self.assertEqual(unknown.messages, conflict.messages)
        self.assertEqual(unknown.messages[0].key, BotMessageKey.UNREGISTERED_PHONE)
        self.assertEqual(unknown.messages[0].parameters, ())
        self.assertIsNone(unknown.state)
        self.assertIsNone(conflict.state)
        self.assertNotIn(CUSTOMER, repr(conflict))
        self.assertNotIn(OTHER, repr(conflict))

    def test_sender_id_is_not_used_as_a_phone(self) -> None:
        directory = _Directory({"+963988100101": (CUSTOMER,)})
        turn = handle_customer_conversation(
            _inbound("1", phone=None, sender="963988100101@c.us"),
            None,
            _context(),
            directory,
            _Orders((_header("DCO-1"),)),
            _Stages(),
            _Routes(),
            _Services(),
        )
        self.assertEqual(turn.messages[0].key, BotMessageKey.UNREGISTERED_PHONE)
        self.assertEqual(directory.calls, 0)

    def test_one_current_order_runs_the_selected_service_without_another_prompt(self) -> None:
        orders = _Orders((_header("DCO-2026-00021"), _header("DCO-OLD", stored_status="Delivered")))
        services = _Services()
        opened, _directory, _services = _run("اهلا", None, orders, services=services)
        turn, _directory, _services = _run("1", opened.state, orders, services=services)
        self.assertEqual(turn.messages[0].key, BotMessageKey.ORDER_STATUS)
        self.assertEqual(dict(turn.messages[0].parameters)["order_name"], "DCO-2026-00021")
        self.assertEqual(
            dict(turn.messages[0].parameters)["public_status"],
            PublicOrderStatus.AWAITING_START,
        )
        self.assertNotIn("DCO-OLD", repr(turn.messages))
        self.assertEqual(services.requests, [])
        self.assertEqual(turn.state.service_id, BotService.ORDER_STATUS)
        self.assertEqual(turn.state.phase, ConversationPhase.AWAITING_ORDER_NUMBER)

    def test_many_orders_are_listed_in_full_and_chosen_by_exact_name(self) -> None:
        rows = tuple(_header(f"DCO-2026-{index:05d}", order_date="2026-10-01") for index in range(1, 26))
        orders = _Orders(rows)
        opened, _directory, _services = _run("start", None, orders)
        listed, _directory, _services = _run("1", opened.state, orders)
        lines = [item for item in listed.messages if item.key == BotMessageKey.CURRENT_ORDER_LINE]
        self.assertEqual(len(lines), 25)
        self.assertEqual(
            [dict(item.parameters)["order_name"] for item in lines],
            [f"DCO-2026-{index:05d}" for index in range(25, 0, -1)],
        )
        chosen, _directory, services = _run("DCO-2026-00002", listed.state, orders)
        self.assertEqual(dict(chosen.messages[0].parameters)["order_name"], "DCO-2026-00002")
        self.assertEqual(services.requests, [])
        self.assertEqual(orders.exact_names[-1], "DCO-2026-00002")

    def test_no_current_orders_then_a_delivered_order_is_accepted(self) -> None:
        orders = _Orders((_header("DCO-DONE", stored_status="Delivered", order_date="2026-09-01"),))
        opened, _directory, _services = _run("hi", None, orders)
        waiting, _directory, _services = _run("1", opened.state, orders)
        self.assertEqual(
            [message.key for message in waiting.messages],
            [BotMessageKey.NO_CURRENT_ORDERS],
        )
        self.assertEqual(orders.exact_names, [])
        selected, _directory, services = _run("  DCO-DONE  ", waiting.state, orders)
        self.assertEqual(selected.messages[0].key, BotMessageKey.ORDER_STATUS)
        self.assertEqual(dict(selected.messages[0].parameters)["public_status"], PublicOrderStatus.DELIVERED)
        self.assertEqual(orders.exact_names, ["DCO-DONE"])
        self.assertEqual(services.requests, [])

    def test_cancelled_order_does_not_reach_the_service_port(self) -> None:
        orders = _Orders((_header("DCO-STOP", stored_status="Cancelled"),))
        services = _Services()
        opened, _directory, _services = _run("hi", None, orders, services=services)
        waiting, _directory, _services = _run("2", opened.state, orders, services=services)
        turn, _directory, _services = _run("DCO-STOP", waiting.state, orders, services=services)
        self.assertEqual(turn.messages[0].key, BotMessageKey.ORDER_CANCELLED)
        self.assertEqual(services.requests, [])
        self.assertEqual(turn.state.service_id, BotService.FINAL_COST)

    def test_option_two_returns_price_and_document_as_separate_outputs(self) -> None:
        result = CustomerServiceResult(
            ServiceResultCode.READY,
            amount=Decimal("125.00"),
            currency="USD",
            documents=(
                CustomerBotDocument(
                    document_type="customer_invoice",
                    filename="فاتورة-DCO-STOP.pdf",
                    mime_type="application/pdf",
                    content=b"%PDF-fake",
                ),
            ),
        )
        services = _Services(result)
        orders = _Orders((_header("DCO-PRICE"),))
        opened, _directory, _services = _run("hi", None, orders, services=services)
        waiting, _directory, _services = _run("2", opened.state, orders, services=services)
        turn, _directory, _services = _run("DCO-PRICE", waiting.state, orders, services=services)
        self.assertEqual(turn.messages[0].key, BotMessageKey.FINAL_PRICE)
        self.assertEqual(dict(turn.messages[0].parameters)["amount"], "125.00")
        self.assertEqual(dict(turn.messages[0].parameters)["currency"], "USD")
        self.assertEqual(turn.documents[0].mime_type, "application/pdf")
        self.assertNotIn("documents", turn.state.to_payload())

    def test_option_three_returns_approved_plan_document_separately(self) -> None:
        result = CustomerServiceResult(
            ServiceResultCode.PLAN_READY,
            documents=(
                CustomerBotDocument(
                    document_type="approved_cutting_plan",
                    filename="خطة-قص-DCO-2026-00021-rev-1.pdf",
                    mime_type="application/pdf",
                    content=b"%PDF-plan",
                ),
            ),
        )
        services = _Services(result)
        orders = _Orders((_header("DCO-2026-00021"),))
        opened, _directory, _services = _run("hi", None, orders)
        waiting, _directory, _services = _run("3", opened.state, orders, services=services)
        turn, _directory, _services = _run(
            "DCO-2026-00021", waiting.state, orders, services=services
        )

        self.assertEqual(turn.messages[0].key, BotMessageKey.APPROVED_PLAN)
        self.assertEqual(
            dict(turn.messages[0].parameters)["order_name"], "DCO-2026-00021"
        )
        self.assertEqual(turn.documents[0].document_type, "approved_cutting_plan")
        self.assertNotIn("documents", turn.state.to_payload())

    def test_delivered_superseded_order_reaches_status_price_and_plan_on_that_document(self) -> None:
        rows = (
            _header("DCO-A"),
            _header("DCO-B"),
            _header("DCO-NEW"),
            _header(
                "DCO-OLD",
                stored_status="Delivered",
                revision_state=RevisionState.SUPERSEDED,
            ),
            _header("DCO-STALE", revision_state=RevisionState.SUPERSEDED),
        )

        class _PlanReader:
            def __init__(self, available: bool) -> None:
                self.available = available
                self.orders: list[str] = []

            def read(self, phone: str, order_name: str):
                self.orders.append(order_name)
                if self.available and order_name == "DCO-OLD":
                    return CustomerBotApprovedPlanSnapshot(
                        available=True,
                        plan_name="CP-OLD",
                        revision=1,
                        source_type="System",
                        consistency_key="same",
                    )
                return None

        class _PlanPdf:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def render(self, order_name: str, plan_name: str) -> bytes:
                self.calls.append((order_name, plan_name))
                return b"%PDF-old"

        def _awaiting(orders: _Orders, digit: str, services):
            opened, _directory, _services = _run("hi", None, orders, services=services)
            return _run(digit, opened.state, orders, services=services)[0]

        reader = _PlanReader(True)
        pdf = _PlanPdf()
        plan = CustomerBotServiceRouter(CustomerBotApprovedPlanService(reader, pdf))
        orders = _Orders(rows)
        listed = _awaiting(orders, "3", plan)
        listed_names = [
            dict(item.parameters)["order_name"]
            for item in listed.messages
            if item.key == BotMessageKey.CURRENT_ORDER_LINE
        ]
        self.assertEqual(listed_names, ["DCO-NEW", "DCO-B", "DCO-A"])
        self.assertEqual(reader.orders, [])
        ready, _directory, _services = _run("DCO-OLD", listed.state, orders, services=plan)
        self.assertEqual(ready.messages[0].key, BotMessageKey.APPROVED_PLAN)
        self.assertEqual(dict(ready.messages[0].parameters)["order_name"], "DCO-OLD")
        self.assertEqual(reader.orders, ["DCO-OLD", "DCO-OLD"])
        self.assertEqual(pdf.calls, [("DCO-OLD", "CP-OLD")])
        self.assertEqual(ready.documents[0].content, b"%PDF-old")
        self.assertNotIn("DCO-NEW", ready.documents[0].filename)
        blocked, _directory, _services = _run("DCO-STALE", ready.state, orders, services=plan)
        self.assertEqual(blocked.messages[0].key, BotMessageKey.ORDER_NOT_CURRENT)
        self.assertEqual(dict(blocked.messages[0].parameters)["order_name"], "DCO-STALE")
        self.assertEqual(blocked.documents, ())
        self.assertEqual(reader.orders, ["DCO-OLD", "DCO-OLD"])
        self.assertEqual(pdf.calls, [("DCO-OLD", "CP-OLD")])

        missing = _PlanReader(False)
        missing_pdf = _PlanPdf()
        unavailable = CustomerBotServiceRouter(
            CustomerBotApprovedPlanService(missing, missing_pdf)
        )
        denied_orders = _Orders(rows)
        denied_list = _awaiting(denied_orders, "3", unavailable)
        denied, _directory, _services = _run(
            "DCO-OLD", denied_list.state, denied_orders, services=unavailable
        )
        self.assertEqual(denied.messages[0].key, BotMessageKey.APPROVED_PLAN_UNAVAILABLE)
        self.assertEqual(denied.documents, ())
        self.assertEqual(missing_pdf.calls, [])
        self.assertEqual(missing.orders, ["DCO-OLD"])

        status_services = _Services()
        status_orders = _Orders(rows)
        status_list = _awaiting(status_orders, "1", status_services)
        status, _directory, _services = _run(
            "DCO-OLD", status_list.state, status_orders, services=status_services
        )
        self.assertEqual(status.messages[0].key, BotMessageKey.ORDER_STATUS)
        self.assertEqual(dict(status.messages[0].parameters)["order_name"], "DCO-OLD")
        self.assertEqual(
            dict(status.messages[0].parameters)["public_status"],
            PublicOrderStatus.DELIVERED,
        )
        self.assertEqual(status.documents, ())
        self.assertEqual(status_services.requests, [])

        class _Price:
            def __init__(self) -> None:
                self.orders: list[str] = []

            def execute(self, request: CustomerServiceRequest) -> CustomerServiceResult:
                if request.service_id != BotService.FINAL_COST:
                    return CustomerServiceResult(ServiceResultCode.UNAVAILABLE)
                self.orders.append(request.order_name)
                return CustomerServiceResult(ServiceResultCode.PRICE_UNAVAILABLE)

        price = _Price()
        price_orders = _Orders(rows)
        price_list = _awaiting(price_orders, "2", price)
        priced, _directory, _services = _run(
            "DCO-OLD", price_list.state, price_orders, services=price
        )
        self.assertEqual(priced.messages[0].key, BotMessageKey.FINAL_PRICE_UNAVAILABLE)
        self.assertEqual(priced.documents, ())
        self.assertEqual(price.orders, ["DCO-OLD"])

    def test_missing_and_foreign_orders_have_the_same_messages(self) -> None:
        orders = _Orders((_header("DCO-FOREIGN", customer=OTHER, stored_status="Delivered"),))
        opened, _directory, _services = _run("hi", None, orders)
        waiting, _directory, _services = _run("1", opened.state, orders)
        missing, _directory, _services = _run("DCO-ABSENT", waiting.state, orders)
        foreign, _directory, _services = _run("DCO-FOREIGN", waiting.state, orders)
        self.assertEqual(missing.messages, foreign.messages)
        self.assertEqual(missing.messages[0].key, BotMessageKey.ORDER_NOT_FOUND)
        self.assertEqual(missing.messages[0].parameters, ())
        self.assertNotIn(OTHER, repr(missing.messages))

    def test_invalid_entry_keeps_the_service_and_a_later_name_works(self) -> None:
        orders = _Orders((_header("DCO-A"), _header("DCO-B")))
        opened, _directory, _services = _run("hi", None, orders)
        waiting, _directory, _services = _run("1", opened.state, orders)
        invalid, _directory, _services = _run("2", waiting.state, orders)
        self.assertEqual(invalid.messages[0].key, BotMessageKey.INVALID_ORDER_NUMBER)
        self.assertEqual(dict(invalid.messages[0].parameters)["return_digit"], "0")
        self.assertEqual(invalid.state.service_id, BotService.ORDER_STATUS)
        self.assertEqual(orders.exact_names, [])
        found, _directory, _services = _run("DCO-B", invalid.state, orders)
        self.assertEqual(dict(found.messages[0].parameters)["order_name"], "DCO-B")

    def test_zero_returns_to_the_menu_from_menu_prompt_and_result(self) -> None:
        orders = _Orders((_header("DCO-1"),))
        opened, _directory, _services = _run("hi", None, orders)
        menu, _directory, _services = _run("0", opened.state, orders)
        self.assertEqual(tuple(item.key for item in menu.messages), (BotMessageKey.MAIN_MENU,))
        self.assertIsNone(menu.state.service_id)
        waiting, _directory, _services = _run("3", menu.state, orders)
        back, _directory, _services = _run("٠", waiting.state, orders)
        self.assertEqual(back.state.phase, ConversationPhase.MAIN_MENU)
        self.assertIsNone(back.state.selected_order_name)
        again, _directory, services = _run("2", back.state, orders)
        home, _directory, _services = _run("0", again.state, orders, services=services)
        self.assertEqual(home.state.phase, ConversationPhase.MAIN_MENU)
        self.assertEqual(services.requests[0].service_id, BotService.FINAL_COST)

    def test_the_same_service_accepts_another_order_number(self) -> None:
        orders = _Orders((_header("DCO-1"), _header("DCO-2")))
        opened, _directory, _services = _run("hi", None, orders)
        waiting, _directory, _services = _run("1", opened.state, orders)
        first, _directory, _services = _run("DCO-1", waiting.state, orders)
        second, _directory, _services = _run("DCO-2", first.state, orders)
        self.assertEqual(first.state.service_id, second.state.service_id)
        self.assertEqual(dict(second.messages[0].parameters)["order_name"], "DCO-2")

    def test_menu_digits_do_not_rewrite_an_order_name(self) -> None:
        orders = _Orders((_header("DCO-1"),))
        opened, _directory, _services = _run("hi", None, orders)
        waiting, _directory, _services = _run("\u0661", opened.state, orders)
        self.assertEqual(waiting.state.service_id, BotService.ORDER_STATUS)
        missed, _directory, _services = _run("DCO-\u0661", waiting.state, orders)
        self.assertEqual(missed.messages[0].key, BotMessageKey.ORDER_NOT_FOUND)
        self.assertEqual(orders.exact_names[-1], "DCO-\u0661")

    def test_a_changed_customer_discards_the_previous_service(self) -> None:
        orders = _Orders((_header("DCO-A"), _header("DCO-B", customer=OTHER)))
        directory = _Directory({PHONE: (CUSTOMER,)})
        opened, _directory, _services = _run("hi", None, orders, directory=directory)
        waiting, _directory, _services = _run("1", opened.state, orders, directory=directory)
        directory.matches = {PHONE: (OTHER,)}
        selections_before = len(orders.exact_names)
        reset, _directory, services = _run(
            "DCO-A", waiting.state, orders, directory=directory, services=_Services()
        )
        self.assertEqual(
            tuple(item.key for item in reset.messages),
            (BotMessageKey.WELCOME, BotMessageKey.MAIN_MENU),
        )
        self.assertEqual(reset.state.customer_id, OTHER)
        self.assertIsNone(reset.state.service_id)
        self.assertEqual(services.requests, [])
        self.assertEqual(len(orders.exact_names), selections_before)

    def test_a_retired_additional_number_gets_no_orders(self) -> None:
        orders = _Orders((_header("DCO-1"),))
        turn, directory, _services = _run(
            "1", None, orders, directory=_Directory({}), phone="+963988100188"
        )
        self.assertEqual(turn.messages[0].key, BotMessageKey.UNREGISTERED_PHONE)
        self.assertEqual(orders.list_calls, 0)
        self.assertEqual(directory.calls, 1)

    def test_expiry_and_sender_isolation_start_a_new_conversation(self) -> None:
        orders = _Orders((_header("DCO-1"), _header("DCO-2")))
        opened, _directory, _services = _run("hi", None, orders)
        waiting, _directory, _services = _run("1", opened.state, orders)
        expired, _directory, _services = _run(
            "DCO-2", waiting.state, orders, when=NOW + TTL
        )
        self.assertEqual(expired.messages[0].key, BotMessageKey.WELCOME)
        self.assertEqual(orders.exact_names, [])
        other_sender, _directory, _services = _run(
            "DCO-2", waiting.state, orders, sender="sender-b"
        )
        self.assertEqual(other_sender.messages[0].key, BotMessageKey.WELCOME)
        self.assertIn("sender-b", other_sender.state.isolation_key)
        self.assertNotIn("sender-b", waiting.state.isolation_key)

    def test_groups_own_messages_and_a_disabled_bot_do_not_read(self) -> None:
        orders = _Orders((_header("DCO-1"),))
        opened, _directory, _services = _run("hi", None, orders)
        for inbound in (
            {"own": True},
            {"group": True},
            {"kind": InboundMessageKind.OTHER},
        ):
            turn = handle_customer_conversation(
                _inbound("1", **inbound),
                opened.state,
                _context(),
                _Exploding(),
                _Exploding(),
                _Exploding(),
                _Exploding(),
                _Exploding(),
            )
            self.assertEqual(turn.messages, ())
            self.assertEqual(turn.state, opened.state)
        disabled = handle_customer_conversation(
            _inbound("1"),
            opened.state,
            _context(enabled=False),
            _Exploding(),
            _Exploding(),
            _Exploding(),
            _Exploding(),
            _Exploding(),
        )
        self.assertEqual(disabled.messages, ())
        self.assertEqual(disabled.state, opened.state)

    def test_unimplemented_services_are_unavailable_and_record_the_phone(self) -> None:
        orders = _Orders((_header("DCO-1"),))
        services = _Services()
        opened, _directory, _services = _run("hi", None, orders, services=services)
        for digit, service_id in (
            ("2", BotService.FINAL_COST),
            ("3", BotService.APPROVED_CUTTING_PLAN),
            ("4", BotService.MEASUREMENTS),
        ):
            turn, _directory, _services = _run(digit, opened.state, orders, services=services)
            self.assertEqual(turn.messages[0].key, BotMessageKey.SERVICE_UNAVAILABLE)
            self.assertEqual(dict(turn.messages[0].parameters)["service_id"], service_id)
            self.assertNotIn("price", dict(turn.messages[0].parameters))
        self.assertEqual(
            [request.service_id for request in services.requests],
            [BotService.FINAL_COST, BotService.APPROVED_CUTTING_PLAN, BotService.MEASUREMENTS],
        )
        self.assertTrue(all(request.phone == PHONE for request in services.requests))
        self.assertNotIn("customer_id", CustomerServiceRequest.__dataclass_fields__)
        unavailable = UnavailableCustomerBotServices().execute(services.requests[0])
        self.assertEqual(unavailable.code, ServiceResultCode.UNAVAILABLE)

    def test_not_current_and_unsupported_stay_explicit(self) -> None:
        orders = _Orders(
            (
                _header("DCO-OLD", revision_state=RevisionState.SUPERSEDED),
                _header(
                    "DCO-ODD",
                    stored_status="Ready for Delivery",
                    production_path="missing",
                    current_stage_name="ST-1",
                ),
            )
        )
        stages = _Stages({"ST-1": ProductionStageFacts("ST-1", "Completed", "last")})
        routes = _Routes({("missing", "last"): None})
        opened = handle_customer_conversation(
            _inbound("hi"), None, _context(), _Directory(), orders, stages, routes, _Services()
        )
        waiting = handle_customer_conversation(
            _inbound("1"), opened.state, _context(), _Directory(), orders, stages, routes, _Services()
        )
        old = handle_customer_conversation(
            _inbound("DCO-OLD"), waiting.state, _context(), _Directory(), orders, stages, routes, _Services()
        )
        odd = handle_customer_conversation(
            _inbound("DCO-ODD"), waiting.state, _context(), _Directory(), orders, stages, routes, _Services()
        )
        self.assertEqual(old.messages[0].key, BotMessageKey.ORDER_NOT_CURRENT)
        self.assertEqual(dict(old.messages[0].parameters), {"order_name": "DCO-OLD"})
        self.assertEqual(dict(odd.messages[0].parameters)["public_status"], PublicOrderStatus.UNSUPPORTED)

    def test_a_foreign_payload_cannot_authorize_or_carry_a_price(self) -> None:
        opened, _directory, _services = _run("hi", None, _Orders((_header("DCO-1"),)))
        payload = opened.state.to_payload()
        self.assertIsNotNone(conversation_state_from_payload(payload))
        payload["price"] = "50"
        self.assertIsNone(conversation_state_from_payload(payload))
        parameters = inspect.signature(handle_customer_conversation).parameters
        self.assertNotIn("customer_id", parameters)
        self.assertIn("phone", inspect.signature(CustomerServiceRequest).parameters)
        self.assertNotIn("customer_id", CustomerServiceRequest.__dataclass_fields__)

    def test_engine_sources_do_not_send_or_compose_arabic_sentences(self) -> None:
        paths = (
            ROOT / "almdina_erp" / "domain" / "customer_bot" / "conversation.py",
            ROOT / "almdina_erp" / "application" / "customer_bot" / "handle_conversation.py",
            ROOT / "almdina_erp" / "application" / "customer_bot" / "conversation_ports.py",
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"[\u0621-\u064A]")
            for forbidden in ("frappe", "whatsapp", "whitelist", "socket", "set_value", "insert("):
                self.assertNotIn(forbidden, source)

    def test_simulation_report_renders_the_five_review_cases(self) -> None:
        report = simulation_report()
        for title in (
            "عميل معروف وطلب واحد",
            "عدة طلبات",
            "طلب مسلّم سابق",
            "رقم غير مسجل",
            "خدمة غير منفذة ثم الرجوع",
        ):
            self.assertIn(title, report)
        self.assertIn("بانتظار بدء العمل.", report)
        self.assertIn("تم التسليم.", report)
        self.assertIn("هذه الخدمة غير متاحة حالياً.", report)
        self.assertNotIn("98765", report)

    def test_invalid_menu_choice_does_not_list_orders(self) -> None:
        orders = _Orders((_header("DCO-1"),))
        opened, _directory, _services = _run("hi", None, orders)
        invalid, _directory, _services = _run("9", opened.state, orders)
        self.assertEqual(invalid.messages[0].key, BotMessageKey.INVALID_MENU_CHOICE)
        self.assertEqual(orders.list_calls, 0)
        self.assertEqual(invalid.state.phase, ConversationPhase.MAIN_MENU)


def simulation_report() -> str:
    """Run the five review transcripts through the engine and the test renderer."""

    sections = []
    sections.append(_simulate_one_order())
    sections.append(_simulate_many_orders())
    sections.append(_simulate_delivered())
    sections.append(_simulate_unregistered())
    sections.append(_simulate_unavailable_then_menu())
    return "\n\n".join(sections)


def _simulate_one_order() -> str:
    orders = _Orders((_header("DCO-2026-00021", order_date="2026-10-18"),))
    return _script("عميل معروف وطلب واحد", orders, ("مرحبا", "1"))


def _simulate_many_orders() -> str:
    orders = _Orders(
        (
            _header("DCO-2026-00030", order_date="2026-10-18"),
            _header("DCO-2026-00012", order_date="2026-10-02"),
        )
    )
    return _script("عدة طلبات", orders, ("مرحبا", "1", "DCO-2026-00012"))


def _simulate_delivered() -> str:
    orders = _Orders((_header("DCO-2026-00008", stored_status="Delivered", order_date="2026-09-15"),))
    return _script("طلب مسلّم سابق", orders, ("مرحبا", "1", "DCO-2026-00008"))


def _simulate_unregistered() -> str:
    return _script("رقم غير مسجل", _Orders(), ("مرحبا",), directory=_Directory({}))


def _simulate_unavailable_then_menu() -> str:
    orders = _Orders((_header("DCO-2026-00021", order_date="2026-10-18"),))
    return _script("خدمة غير منفذة ثم الرجوع", orders, ("مرحبا", "2", "0"))


def _script(title: str, orders: _Orders, lines: tuple[str, ...], directory: _Directory | None = None) -> str:
    state = None
    rendered = [title]
    for line in lines:
        turn, _directory, _services = _run(line, state, orders, directory=directory)
        state = turn.state
        rendered.append(f"العميل: {line}")
        rendered.append(render_turn(turn.messages))
    return "\n".join(rendered)


if __name__ == "__main__":
    print(simulation_report())
    unittest.main()
