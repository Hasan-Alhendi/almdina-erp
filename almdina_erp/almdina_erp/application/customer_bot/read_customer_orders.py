"""List a customer's current orders and select one by its full name.

Every call resolves the phone against the current primary number again.
A customer id, an ownership flag, or an older identity result is not an input.
"""

from __future__ import annotations

from collections.abc import Mapping

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
    non_current_revision_states,
    owned_revision_is_current,
)

from .order_followup_ports import (
    CustomerOrderHeader,
    CustomerOrderHeaderReader,
    ProductionRouteCatalog,
    ProductionStageFacts,
    ProductionStageReader,
)
from .phone_access_ports import CustomerPhoneDirectory
from .resolve_customer_identity import resolve_customer_identity

_EXCLUDED_LIST_STATUSES = frozenset({PublicOrderStatus.DELIVERED, PublicOrderStatus.CANCELLED})


def list_current_customer_orders(
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    phone: str,
) -> CurrentOrderList:
    identity = resolve_customer_identity(directory, phone)
    if identity.code != IdentityCode.ALLOWED or not identity.customer_id:
        return CurrentOrderList(
            CurrentOrderListOutcome.IDENTITY_UNAVAILABLE,
            identity.code,
        )
    records = tuple(
        header
        for header in headers.list_current_headers(identity.customer_id)
        if header.customer_id == identity.customer_id
        and owned_revision_is_current(header.revision_state)
        and header.revision_state not in non_current_revision_states()
    )
    summaries = _summaries(records, stages, routes, listed=True)
    if not summaries:
        return CurrentOrderList(CurrentOrderListOutcome.NONE, identity.code)
    if len(summaries) == 1:
        return CurrentOrderList(CurrentOrderListOutcome.ONE, identity.code, (summaries[0],))
    return CurrentOrderList(CurrentOrderListOutcome.MANY, identity.code, tuple(summaries))


def select_customer_order_by_name(
    directory: CustomerPhoneDirectory,
    headers: CustomerOrderHeaderReader,
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    phone: str,
    order_name: str,
) -> OrderSelection:
    identity = resolve_customer_identity(directory, phone)
    if identity.code != IdentityCode.ALLOWED or not identity.customer_id:
        return OrderSelection(OrderSelectionOutcome.IDENTITY_UNAVAILABLE, identity.code)
    token = _exact_order_token(order_name)
    if token is None:
        return OrderSelection(OrderSelectionOutcome.NOT_FOUND, identity.code)
    header = headers.get_header_by_exact_name(token)
    if (
        header is None
        or header.name != token
        or header.customer_id != identity.customer_id
    ):
        return OrderSelection(OrderSelectionOutcome.NOT_FOUND, identity.code)
    status = _status_for((header,), stages, routes)[header.name]
    if status == PublicOrderStatus.CANCELLED:
        return OrderSelection(
            OrderSelectionOutcome.CANCELLED,
            identity.code,
            order_name=header.name,
            order_date=_date_text(header.order_date),
            public_status=PublicOrderStatus.CANCELLED,
        )
    if status == PublicOrderStatus.DELIVERED:
        return OrderSelection(
            OrderSelectionOutcome.SELECTED,
            identity.code,
            order_name=header.name,
            order_date=_date_text(header.order_date),
            public_status=PublicOrderStatus.DELIVERED,
        )
    if not owned_revision_is_current(header.revision_state):
        return OrderSelection(
            OrderSelectionOutcome.NOT_CURRENT,
            identity.code,
            order_name=header.name,
        )
    return OrderSelection(
        OrderSelectionOutcome.SELECTED,
        identity.code,
        order_name=header.name,
        order_date=_date_text(header.order_date),
        public_status=status,
    )


def _summaries(
    records: tuple[CustomerOrderHeader, ...],
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
    *,
    listed: bool,
) -> list[CustomerOrderSummary]:
    statuses = _status_for(records, stages, routes)
    summaries: list[CustomerOrderSummary] = []
    for header in records:
        status = statuses[header.name]
        if listed and status in _EXCLUDED_LIST_STATUSES:
            continue
        if not listed:
            continue
        summaries.append(
            CustomerOrderSummary(
                order_name=header.name,
                order_date=_date_text(header.order_date),
                public_status=status,
            )
        )
    summaries.sort(
        key=lambda item: (
            item.order_date is not None,
            item.order_date or "",
            item.order_name,
        ),
        reverse=True,
    )
    return summaries


def _status_for(
    records: tuple[CustomerOrderHeader, ...],
    stages: ProductionStageReader,
    routes: ProductionRouteCatalog,
) -> dict[str, str]:
    pointers = tuple(
        dict.fromkeys(
            (header.name, header.current_stage_name)
            for header in records
            if header.current_stage_name
        )
    )
    stage_rows = stages.stages_for_orders(pointers) if pointers else {}
    keys = tuple(
        dict.fromkeys(
            (header.production_path, stage.stage_type)
            for header in records
            if header.production_path
            and (stage := stage_rows.get(header.current_stage_name)) is not None
            and stage.stage_type
        )
    )
    terminals = routes.terminal_by_path_and_stage(keys) if keys else {}
    statuses: dict[str, str] = {}
    for header in records:
        stage = stage_rows.get(header.current_stage_name) if header.current_stage_name else None
        statuses[header.name] = classify_public_order_status(
            _facts(header, stage, terminals)
        )
    return statuses


def _facts(
    header: CustomerOrderHeader,
    stage: ProductionStageFacts | None,
    terminals: Mapping[tuple[str, str], bool | None],
) -> OrderStatusFacts:
    stage_type = stage.stage_type if stage is not None else ""
    route_terminal = None
    if header.production_path and stage_type:
        route_terminal = terminals.get((header.production_path, stage_type))
    return OrderStatusFacts(
        stored_status=header.stored_status,
        production_path=header.production_path,
        current_stage_name=header.current_stage_name,
        stage_row_name=stage.name if stage is not None else "",
        stage_status=stage.status if stage is not None else "",
        stage_type=stage_type,
        route_terminal=route_terminal,
    )


def _date_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text[:10] if text else None


def _exact_order_token(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token or any(character.isspace() for character in token):
        return None
    if any(character in token for character in "%_*?"):
        return None
    return token


__all__ = [
    "list_current_customer_orders",
    "select_customer_order_by_name",
]
