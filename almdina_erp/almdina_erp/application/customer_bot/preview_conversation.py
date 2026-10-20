"""Preview one conversation turn with the real engine and sample orders.

The sample world is built in memory. Preview always runs with an enabled
context of its own and does not read or write the stored switch. Services
2, 3, and 4 stay unavailable.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from almdina_erp.almdina_erp.application.customer_bot.conversation_ports import (
    UnavailableCustomerBotServices,
)
from almdina_erp.almdina_erp.application.customer_bot.handle_conversation import (
    handle_customer_conversation,
)
from almdina_erp.almdina_erp.application.customer_bot.order_followup_ports import (
    CustomerOrderHeader,
)
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    ConversationContext,
    ConversationState,
    conversation_state_from_payload,
)
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundMessageKind,
    build_inbound_customer_message,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
    TemplateIssue,
    explain_messages,
    validate_texts,
)
from almdina_erp.almdina_erp.domain.orders.revisions import RevisionState


PREVIEW_SCENARIOS = (
    "unknown_number",
    "no_orders",
    "one_order",
    "many_orders",
    "delivered_order",
    "cancelled_order",
)
PREVIEW_PHONE = "+963900000001"
UNKNOWN_PHONE = "+963900000099"
PREVIEW_CUSTOMER = "PREVIEW-CUSTOMER"
PREVIEW_CONNECTION = "preview"
PREVIEW_CONVERSATION = "preview"
PREVIEW_SENDER = "preview-sender"
_MAX_TEXT = 500
_TTL = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class PreviewResult:
    ok: bool
    code: str
    lines: tuple[str, ...]
    state: dict[str, str | None] | None
    issues: tuple[TemplateIssue, ...]


def preview_customer_bot_turn(
    texts: Mapping[str, str],
    scenario: str,
    text: str,
    state_payload: object,
    now: datetime,
    *,
    engine: Callable = handle_customer_conversation,
) -> PreviewResult:
    if scenario not in PREVIEW_SCENARIOS:
        return PreviewResult(False, "invalid_scenario", (), None, ())
    if not isinstance(text, str) or not text.strip():
        return PreviewResult(False, "empty_message", (), None, ())
    if len(text) > _MAX_TEXT:
        return PreviewResult(False, "invalid_message", (), None, ())
    if not isinstance(now, datetime) or now.utcoffset() is None:
        return PreviewResult(False, "invalid_clock", (), None, ())
    issues = validate_texts(texts)
    if issues:
        return PreviewResult(False, "invalid_texts", (), None, issues)
    state = _state(state_payload)
    if state_payload not in (None, "", {}) and state is None:
        return PreviewResult(False, "invalid_state", (), None, ())
    directory = _Directory(_phone_for(scenario))
    orders = _Orders(_rows_for(scenario))
    message = build_inbound_customer_message(
        connection_ref=PREVIEW_CONNECTION,
        provider_event_id=f"preview-{int(now.timestamp() * 1000)}-{abs(hash(text)) % 100000}",
        conversation_id=PREVIEW_CONVERSATION,
        sender_id=PREVIEW_SENDER,
        occurred_at=now,
        kind=InboundMessageKind.TEXT,
        text=text,
        from_own_account=False,
        is_group=False,
        trusted_normalized_phone=_phone_for(scenario),
    )
    turn = engine(
        message,
        state,
        ConversationContext(enabled=True, now=now, session_ttl=_TTL),
        directory,
        orders,
        _Stages(),
        _Routes(),
        UnavailableCustomerBotServices(),
    )
    rendered = explain_messages(texts, turn.messages)
    if isinstance(rendered, TemplateIssue):
        return PreviewResult(False, "render_failed", (), None, (rendered,))
    payload = turn.state.to_payload() if turn.state is not None else None
    return PreviewResult(True, "ok", rendered, payload, ())


def _state(payload: object) -> ConversationState | None:
    if payload in (None, "", {}):
        return None
    return conversation_state_from_payload(payload)


def _phone_for(scenario: str) -> str:
    if scenario == "unknown_number":
        return UNKNOWN_PHONE
    return PREVIEW_PHONE


def _rows_for(scenario: str) -> tuple[CustomerOrderHeader, ...]:
    if scenario in {"unknown_number", "no_orders"}:
        return ()
    if scenario == "one_order":
        return (_header("PREVIEW-DCO-00001", "Draft", "2026-10-18"),)
    if scenario == "many_orders":
        return (
            _header("PREVIEW-DCO-00002", "Draft", "2026-10-18"),
            _header("PREVIEW-DCO-00001", "Draft", "2026-10-02"),
        )
    if scenario == "delivered_order":
        return (_header("PREVIEW-DCO-DELIVERED", "Delivered", "2026-09-15"),)
    return (_header("PREVIEW-DCO-CANCELLED", "Cancelled", "2026-09-01"),)


def _header(name: str, stored_status: str, order_date: str) -> CustomerOrderHeader:
    return CustomerOrderHeader(
        name=name,
        customer_id=PREVIEW_CUSTOMER,
        order_date=order_date,
        stored_status=stored_status,
        revision_state=RevisionState.CURRENT,
        production_path="",
        current_stage_name="",
    )


class _Directory:
    def __init__(self, phone: str) -> None:
        self.phone = phone

    def find_by_normalized_phone(self, normalized_phone: str) -> tuple[str, ...]:
        if normalized_phone == PREVIEW_PHONE and self.phone == PREVIEW_PHONE:
            return (PREVIEW_CUSTOMER,)
        return ()

    def customer_exists(self, customer_id: str) -> bool:
        return customer_id == PREVIEW_CUSTOMER


class _Orders:
    def __init__(self, rows: tuple[CustomerOrderHeader, ...]) -> None:
        self.rows = rows

    def list_current_headers(self, customer_id: str) -> tuple[CustomerOrderHeader, ...]:
        return tuple(row for row in self.rows if row.customer_id == customer_id)

    def get_header_by_exact_name(self, order_name: str) -> CustomerOrderHeader | None:
        for row in self.rows:
            if row.name == order_name:
                return row
        return None


class _Stages:
    def stages_for_orders(self, pointers: tuple[tuple[str, str], ...]) -> dict[str, object]:
        return {}


class _Routes:
    def terminal_by_path_and_stage(
        self, keys: tuple[tuple[str, str], ...]
    ) -> dict[tuple[str, str], bool | None]:
        return {key: None for key in keys}


def preview_clock() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "PREVIEW_SCENARIOS",
    "PreviewResult",
    "preview_clock",
    "preview_customer_bot_turn",
]
