"""Conversation state and message keys for the customer bot.

Digits select a service. Display sentences stay outside this module.
The state remembers the phase and the selected service. It does not store
orders, prices, or files, and it does not prove who the sender is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .checks import required_bool, required_token
from .documents import CustomerBotDocument


class BotService:
    ORDER_STATUS = "order_status"
    FINAL_COST = "final_cost"
    APPROVED_CUTTING_PLAN = "approved_cutting_plan"
    MEASUREMENTS = "measurements"


class ConversationPhase:
    MAIN_MENU = "main_menu"
    AWAITING_ORDER_NUMBER = "awaiting_order_number"


class BotMessageKey:
    WELCOME = "welcome"
    MAIN_MENU = "main_menu"
    UNREGISTERED_PHONE = "unregistered_phone"
    INVALID_MENU_CHOICE = "invalid_menu_choice"
    NO_CURRENT_ORDERS = "no_current_orders"
    ASK_ORDER_NUMBER = "ask_order_number"
    CURRENT_ORDER_LINE = "current_order_line"
    ORDER_STATUS = "order_status"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_NOT_FOUND = "order_not_found"
    ORDER_NOT_CURRENT = "order_not_current"
    INVALID_ORDER_NUMBER = "invalid_order_number"
    SERVICE_UNAVAILABLE = "service_unavailable"
    FINAL_PRICE = "final_price"
    FINAL_PRICE_UNAVAILABLE = "final_price_unavailable"
    INVOICE_FAILED = "invoice_failed"
    PRICE_DATA_CHANGED = "price_data_changed"
    APPROVED_PLAN = "approved_plan"
    APPROVED_PLAN_UNAVAILABLE = "approved_plan_unavailable"
    PLAN_PDF_FAILED = "plan_pdf_failed"
    PLAN_DATA_CHANGED = "plan_data_changed"


class ServiceResultCode:
    UNAVAILABLE = "service_unavailable"
    READY = "ready"
    PRICE_UNAVAILABLE = "price_unavailable"
    INVOICE_FAILED = "invoice_failed"
    PRICE_DATA_CHANGED = "price_data_changed"
    PLAN_READY = "plan_ready"
    PLAN_UNAVAILABLE = "plan_unavailable"
    PLAN_PDF_FAILED = "plan_pdf_failed"
    PLAN_DATA_CHANGED = "plan_data_changed"


_SERVICE_BY_DIGIT = {
    "1": BotService.ORDER_STATUS,
    "2": BotService.FINAL_COST,
    "3": BotService.APPROVED_CUTTING_PLAN,
    "4": BotService.MEASUREMENTS,
}
_MENU_DIGITS = {
    "0": "0",
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "\u0660": "0",
    "\u0661": "1",
    "\u0662": "2",
    "\u0663": "3",
    "\u0664": "4",
    "\u06f0": "0",
    "\u06f1": "1",
    "\u06f2": "2",
    "\u06f3": "3",
    "\u06f4": "4",
}
_LATER_SERVICES = frozenset(
    {
        BotService.FINAL_COST,
        BotService.APPROVED_CUTTING_PLAN,
        BotService.MEASUREMENTS,
    }
)
_PARAMETER_NAMES = frozenset(
    {
        "service_id",
        "order_name",
        "order_date",
        "public_status",
        "return_digit",
        "amount",
        "currency",
    }
)
_STATE_FIELDS = frozenset(
    {
        "isolation_key",
        "phase",
        "service_id",
        "selected_order_name",
        "customer_id",
        "expires_at",
    }
)


def menu_command(text: object) -> str | None:
    """Return 0-4 when the whole message is a menu digit.

    Arabic-Indic and Eastern Arabic-Indic digits count. Any other text,
    including an order name, is left unchanged and returns None.
    """

    if not isinstance(text, str):
        return None
    return _MENU_DIGITS.get(text.strip())


def service_for_menu_digit(digit: str) -> str | None:
    return _SERVICE_BY_DIGIT.get(digit)


def conversation_isolation_key(
    connection_ref: str,
    conversation_id: str,
    sender_id: str,
) -> str:
    return "\n".join((connection_ref, conversation_id, sender_id))


@dataclass(frozen=True, slots=True)
class ConversationContext:
    enabled: bool
    now: datetime
    session_ttl: timedelta

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", required_bool(self.enabled, "enabled"))
        if not isinstance(self.now, datetime) or self.now.utcoffset() is None:
            raise ValueError("now must be a timezone-aware datetime")
        if not isinstance(self.session_ttl, timedelta) or self.session_ttl <= timedelta(0):
            raise ValueError("session_ttl must be a positive duration")


@dataclass(frozen=True, slots=True)
class BotMessage:
    key: str
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.key not in _MESSAGE_KEYS:
            raise ValueError("unknown conversation message key")
        names = [name for name, _value in self.parameters]
        if len(names) != len(set(names)) or any(name not in _PARAMETER_NAMES for name in names):
            raise ValueError("conversation parameters are limited to the public names")
        if any(not isinstance(value, str) for _name, value in self.parameters):
            raise ValueError("conversation parameter values must be strings")


@dataclass(frozen=True, slots=True)
class ConversationState:
    isolation_key: str
    phase: str
    customer_id: str
    expires_at: datetime
    service_id: str | None = None
    selected_order_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.isolation_key, str) or self.isolation_key.count("\n") != 2:
            raise ValueError("isolation_key must bind connection, conversation, and sender")
        if self.phase not in {ConversationPhase.MAIN_MENU, ConversationPhase.AWAITING_ORDER_NUMBER}:
            raise ValueError("unknown conversation phase")
        object.__setattr__(self, "customer_id", required_token(self.customer_id, "customer_id"))
        if not isinstance(self.expires_at, datetime) or self.expires_at.utcoffset() is None:
            raise ValueError("expires_at must be a timezone-aware datetime")
        if self.service_id is not None and self.service_id not in _SERVICE_BY_DIGIT.values():
            raise ValueError("unknown conversation service")
        if self.selected_order_name is not None:
            selected = required_token(self.selected_order_name, "selected_order_name")
            if any(character.isspace() for character in selected):
                raise ValueError("selected_order_name cannot contain whitespace")
            object.__setattr__(self, "selected_order_name", selected)
        if self.phase == ConversationPhase.MAIN_MENU and (
            self.service_id is not None or self.selected_order_name is not None
        ):
            raise ValueError("the main menu does not keep a service or an order")
        if self.phase == ConversationPhase.AWAITING_ORDER_NUMBER and self.service_id is None:
            raise ValueError("waiting for an order number requires a service")

    def to_payload(self) -> dict[str, str | None]:
        return {
            "isolation_key": self.isolation_key,
            "phase": self.phase,
            "service_id": self.service_id,
            "selected_order_name": self.selected_order_name,
            "customer_id": self.customer_id,
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    state: ConversationState | None
    messages: tuple[BotMessage, ...]
    documents: tuple[CustomerBotDocument, ...] = ()


def conversation_state_from_payload(payload: object) -> ConversationState | None:
    """Build a state only from the known fields.

    Extra fields are refused. A parsed state still does not authorize a
    later turn; the engine resolves the phone again.
    """

    if not isinstance(payload, dict) or set(payload) != _STATE_FIELDS:
        return None
    expires_at = payload.get("expires_at")
    service_id = payload.get("service_id")
    selected_order_name = payload.get("selected_order_name")
    if not isinstance(expires_at, str):
        return None
    if service_id is not None and not isinstance(service_id, str):
        return None
    if selected_order_name is not None and not isinstance(selected_order_name, str):
        return None
    try:
        return ConversationState(
            isolation_key=str(payload.get("isolation_key") or ""),
            phase=str(payload.get("phase") or ""),
            customer_id=str(payload.get("customer_id") or ""),
            expires_at=datetime.fromisoformat(expires_at),
            service_id=service_id,
            selected_order_name=selected_order_name,
        )
    except (TypeError, ValueError):
        return None


def later_service_ids() -> frozenset[str]:
    return _LATER_SERVICES


_MESSAGE_KEYS = frozenset(
    value
    for name, value in vars(BotMessageKey).items()
    if name.isupper() and isinstance(value, str)
)


__all__ = [
    "BotMessage",
    "BotMessageKey",
    "BotService",
    "ConversationContext",
    "ConversationPhase",
    "ConversationState",
    "ConversationTurn",
    "ServiceResultCode",
    "conversation_isolation_key",
    "conversation_state_from_payload",
    "later_service_ids",
    "menu_command",
    "service_for_menu_digit",
]
