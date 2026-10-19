"""Advance one customer-bot conversation turn.

The engine does not send, render Arabic, store a session, or build a file.
A disabled context returns before any identity or order call.
"""

from __future__ import annotations

from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    BotMessage,
    BotMessageKey,
    BotService,
    ConversationContext,
    ConversationPhase,
    ConversationState,
    ConversationTurn,
    conversation_isolation_key,
    menu_command,
    service_for_menu_digit,
)
from almdina_erp.almdina_erp.domain.customer_bot.identity import IdentityCode
from almdina_erp.almdina_erp.domain.customer_bot.inbound_message import (
    InboundCustomerMessage,
    InboundMessageKind,
)
from almdina_erp.almdina_erp.domain.customer_bot.order_followup import (
    CurrentOrderListOutcome,
    CustomerOrderSummary,
    OrderSelection,
    OrderSelectionOutcome,
    PublicOrderStatus,
)

from .conversation_ports import CustomerBotServicePort, CustomerServiceRequest
from .order_followup_ports import (
    CustomerOrderHeaderReader,
    ProductionRouteCatalog,
    ProductionStageReader,
)
from .phone_access_ports import CustomerPhoneDirectory
from .read_customer_orders import (
    list_current_customer_orders,
    select_customer_order_by_name,
)
from .resolve_customer_identity import resolve_customer_identity


def handle_customer_conversation(
    message: InboundCustomerMessage,
    state: ConversationState | None,
    context: ConversationContext,
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    services: CustomerBotServicePort,
) -> ConversationTurn:
    if not context.enabled or not _processable(message):
        return ConversationTurn(state, ())
    phone = message.normalized_phone
    if phone is None:
        return ConversationTurn(None, (_message(BotMessageKey.UNREGISTERED_PHONE),))
    identity = resolve_customer_identity(directory, phone)
    if identity.code != IdentityCode.ALLOWED or not identity.customer_id:
        return ConversationTurn(None, (_message(BotMessageKey.UNREGISTERED_PHONE),))
    active = _usable_state(state, message, identity.customer_id, context)
    if active is None:
        return _begin(message, identity.customer_id, context)
    if active.phase == ConversationPhase.MAIN_MENU:
        return _from_menu(
            message, active, context, directory, headers, stages, routes, services, phone
        )
    return _from_order_prompt(
        message, active, context, directory, headers, stages, routes, services, phone
    )


def _processable(message: InboundCustomerMessage) -> bool:
    return (
        message.kind is InboundMessageKind.TEXT
        and not message.from_own_account
        and not message.is_group
    )


def _usable_state(
    state: ConversationState | None,
    message: InboundCustomerMessage,
    customer_id: str,
    context: ConversationContext,
) -> ConversationState | None:
    if state is None:
        return None
    key = conversation_isolation_key(
        message.connection_ref, message.conversation_id, message.sender_id
    )
    if state.isolation_key != key or state.customer_id != customer_id:
        return None
    if state.expires_at <= context.now:
        return None
    return state


def _begin(
    message: InboundCustomerMessage,
    customer_id: str,
    context: ConversationContext,
) -> ConversationTurn:
    return ConversationTurn(
        _fresh(message, context, customer_id, ConversationPhase.MAIN_MENU, None, None),
        (
            _message(BotMessageKey.WELCOME),
            _message(BotMessageKey.MAIN_MENU),
        ),
    )


def _from_menu(
    message: InboundCustomerMessage,
    state: ConversationState,
    context: ConversationContext,
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    services: CustomerBotServicePort,
    phone: str,
) -> ConversationTurn:
    command = menu_command(message.text)
    if command == "0":
        return _main_menu(message, state.customer_id, context)
    service_id = service_for_menu_digit(command or "")
    if service_id is None:
        return ConversationTurn(
            _fresh(message, context, state.customer_id, ConversationPhase.MAIN_MENU, None, None),
            (_message(BotMessageKey.INVALID_MENU_CHOICE),),
        )
    return _open_service(
        message, context, state.customer_id, service_id, directory, headers, stages, routes, services, phone
    )


def _from_order_prompt(
    message: InboundCustomerMessage,
    state: ConversationState,
    context: ConversationContext,
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    services: CustomerBotServicePort,
    phone: str,
) -> ConversationTurn:
    command = menu_command(message.text)
    service_id = state.service_id or ""
    if command == "0":
        return _main_menu(message, state.customer_id, context)
    if command is not None:
        return ConversationTurn(
            _fresh(
                message,
                context,
                state.customer_id,
                ConversationPhase.AWAITING_ORDER_NUMBER,
                service_id,
                state.selected_order_name,
            ),
            (_message(BotMessageKey.INVALID_ORDER_NUMBER, (("return_digit", "0"),)),),
        )
    return _select_typed_order(
        message,
        context,
        state.customer_id,
        service_id,
        state.selected_order_name,
        message.text,
        directory,
        headers,
        stages,
        routes,
        services,
        phone,
    )


def _open_service(
    message: InboundCustomerMessage,
    context: ConversationContext,
    customer_id: str,
    service_id: str,
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    services: CustomerBotServicePort,
    phone: str,
) -> ConversationTurn:
    listed = list_current_customer_orders(directory, headers, stages, routes, phone)
    if listed.outcome == CurrentOrderListOutcome.NONE:
        return ConversationTurn(
            _fresh(
                message,
                context,
                customer_id,
                ConversationPhase.AWAITING_ORDER_NUMBER,
                service_id,
                None,
            ),
            (
                _message(BotMessageKey.NO_CURRENT_ORDERS, (("service_id", service_id),)),
                _message(BotMessageKey.ASK_ORDER_NUMBER, (("service_id", service_id),)),
            ),
        )
    if listed.outcome == CurrentOrderListOutcome.ONE:
        return _select_typed_order(
            message,
            context,
            customer_id,
            service_id,
            None,
            listed.orders[0].order_name,
            directory,
            headers,
            stages,
            routes,
            services,
            phone,
        )
    if listed.outcome == CurrentOrderListOutcome.MANY:
        lines = tuple(_order_line(item) for item in listed.orders)
        return ConversationTurn(
            _fresh(
                message,
                context,
                customer_id,
                ConversationPhase.AWAITING_ORDER_NUMBER,
                service_id,
                None,
            ),
            lines + (_message(BotMessageKey.ASK_ORDER_NUMBER, (("service_id", service_id),)),),
        )
    return ConversationTurn(None, (_message(BotMessageKey.UNREGISTERED_PHONE),))


def _select_typed_order(
    message: InboundCustomerMessage,
    context: ConversationContext,
    customer_id: str,
    service_id: str,
    previous_order_name: str | None,
    order_text: str,
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    services: CustomerBotServicePort,
    phone: str,
) -> ConversationTurn:
    selection = select_customer_order_by_name(
        directory, headers, stages, routes, phone, order_text
    )
    if selection.outcome == OrderSelectionOutcome.IDENTITY_UNAVAILABLE:
        return ConversationTurn(None, (_message(BotMessageKey.UNREGISTERED_PHONE),))
    selected_name = previous_order_name
    if selection.outcome == OrderSelectionOutcome.NOT_FOUND:
        body = (_message(BotMessageKey.ORDER_NOT_FOUND),)
    elif selection.outcome == OrderSelectionOutcome.CANCELLED:
        selected_name = selection.order_name
        body = (_message(BotMessageKey.ORDER_CANCELLED, (("order_name", selection.order_name or ""),)),)
    elif selection.outcome == OrderSelectionOutcome.NOT_CURRENT:
        selected_name = selection.order_name
        body = (_message(BotMessageKey.ORDER_NOT_CURRENT, (("order_name", selection.order_name or ""),)),)
    else:
        selected_name = selection.order_name
        body = (_service_message(service_id, selection, services, phone),)
    return ConversationTurn(
        _fresh(
            message,
            context,
            customer_id,
            ConversationPhase.AWAITING_ORDER_NUMBER,
            service_id,
            selected_name,
        ),
        body + (_message(BotMessageKey.ASK_ORDER_NUMBER, (("service_id", service_id),)),),
    )


def _service_message(
    service_id: str,
    selection: OrderSelection,
    services: CustomerBotServicePort,
    phone: str,
) -> BotMessage:
    order_name = selection.order_name or ""
    if service_id == BotService.ORDER_STATUS:
        return _message(
            BotMessageKey.ORDER_STATUS,
            (
                ("order_name", order_name),
                ("public_status", selection.public_status or PublicOrderStatus.UNSUPPORTED),
            ),
        )
    services.execute(
        CustomerServiceRequest(phone=phone, service_id=service_id, order_name=order_name)
    )
    return _message(
        BotMessageKey.SERVICE_UNAVAILABLE,
        (("service_id", service_id), ("order_name", order_name)),
    )


def _main_menu(
    message: InboundCustomerMessage,
    customer_id: str,
    context: ConversationContext,
) -> ConversationTurn:
    return ConversationTurn(
        _fresh(message, context, customer_id, ConversationPhase.MAIN_MENU, None, None),
        (_message(BotMessageKey.MAIN_MENU),),
    )


def _fresh(
    message: InboundCustomerMessage,
    context: ConversationContext,
    customer_id: str,
    phase: str,
    service_id: str | None,
    selected_order_name: str | None,
) -> ConversationState:
    return ConversationState(
        isolation_key=conversation_isolation_key(
            message.connection_ref, message.conversation_id, message.sender_id
        ),
        phase=phase,
        customer_id=customer_id,
        expires_at=context.now + context.session_ttl,
        service_id=service_id,
        selected_order_name=selected_order_name,
    )


def _order_line(item: CustomerOrderSummary) -> BotMessage:
    parameters = [("order_name", item.order_name)]
    if item.order_date:
        parameters.append(("order_date", item.order_date))
    parameters.append(("public_status", item.public_status))
    return _message(BotMessageKey.CURRENT_ORDER_LINE, tuple(parameters))


def _message(key: str, parameters: tuple[tuple[str, str], ...] = ()) -> BotMessage:
    return BotMessage(key, parameters)


__all__ = ["handle_customer_conversation"]
