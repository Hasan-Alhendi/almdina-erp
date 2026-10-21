"""Editable customer-bot texts and a plain-text renderer.

The catalog is derived from the conversation engine. Digits 1-4 stay fixed
and the main menu is composed from those digits plus the service titles.
Templates accept only named placeholders. They cannot read attributes,
indexes, or call functions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from .conversation import (
    BotMessage,
    BotMessageKey,
    BotService,
    service_for_menu_digit,
)
from .order_followup import PublicOrderStatus


MAX_MESSAGE_LENGTH = 500
MAX_LABEL_LENGTH = 180
_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_MESSAGE_FIELDS: tuple[tuple[str, str, frozenset[str], int], ...] = (
    (BotMessageKey.WELCOME, "welcome_menu", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.INVALID_MENU_CHOICE, "welcome_menu", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.NO_CURRENT_ORDERS, "orders", frozenset({"service_id"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.ASK_ORDER_NUMBER, "orders", frozenset({"service_id"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.CURRENT_ORDER_LINE, "orders", frozenset({"order_name", "order_date", "public_status"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.ORDER_NOT_FOUND, "orders", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.ORDER_NOT_CURRENT, "orders", frozenset({"order_name"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.ORDER_CANCELLED, "orders", frozenset({"order_name"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.ORDER_STATUS, "statuses", frozenset({"order_name", "public_status"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.FINAL_PRICE, "statuses", frozenset({"order_name", "amount", "currency"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.FINAL_PRICE_UNAVAILABLE, "guidance", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.INVOICE_FAILED, "guidance", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.PRICE_DATA_CHANGED, "guidance", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.APPROVED_PLAN, "statuses", frozenset({"order_name"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.APPROVED_PLAN_UNAVAILABLE, "guidance", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.PLAN_PDF_FAILED, "guidance", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.PLAN_DATA_CHANGED, "guidance", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.UNREGISTERED_PHONE, "guidance", frozenset(), MAX_MESSAGE_LENGTH),
    (BotMessageKey.INVALID_ORDER_NUMBER, "guidance", frozenset({"return_digit"}), MAX_MESSAGE_LENGTH),
    (BotMessageKey.SERVICE_UNAVAILABLE, "guidance", frozenset({"service_id", "order_name"}), MAX_MESSAGE_LENGTH),
)
MENU_ENTRIES: tuple[tuple[str, str], ...] = (
    ("1", BotService.ORDER_STATUS),
    ("2", BotService.FINAL_COST),
    ("3", BotService.APPROVED_CUTTING_PLAN),
    ("4", BotService.MEASUREMENTS),
)
GROUP_ORDER = ("welcome_menu", "orders", "statuses", "guidance")
VARIABLE_NAMES = (
    "order_name",
    "order_date",
    "public_status",
    "service_id",
    "return_digit",
    "amount",
    "currency",
)


@dataclass(frozen=True, slots=True)
class TemplateField:
    key: str
    group: str
    variables: frozenset[str]
    max_length: int


@dataclass(frozen=True, slots=True)
class TemplateIssue:
    key: str
    code: str
    detail: str


class CustomerTextRenderError(Exception):
    """A customer-facing render failed closed.

    The message is generic. It does not name a template key or include a
    traceback, and no partial reply is available.
    """

    def __str__(self) -> str:
        return "Customer bot text could not be rendered."


def service_title_key(service_id: str) -> str:
    return f"service_title.{service_id}"


def status_label_key(status: str) -> str:
    return f"status_label.{status}"


def template_fields() -> tuple[TemplateField, ...]:
    fields = [
        TemplateField(key, group, variables, limit)
        for key, group, variables, limit in _MESSAGE_FIELDS
    ]
    fields.extend(
        TemplateField(service_title_key(service_id), "welcome_menu", frozenset(), MAX_LABEL_LENGTH)
        for _digit, service_id in MENU_ENTRIES
    )
    fields.extend(
        TemplateField(status_label_key(status), "statuses", frozenset(), MAX_LABEL_LENGTH)
        for status in _public_statuses()
    )
    return tuple(fields)


def catalog_keys() -> tuple[str, ...]:
    return tuple(field.key for field in template_fields())


def field_by_key() -> dict[str, TemplateField]:
    return {field.key: field for field in template_fields()}


def validate_texts(texts: object) -> tuple[TemplateIssue, ...]:
    if not isinstance(texts, Mapping):
        return (TemplateIssue("", "not_text", "texts must be an object"),)
    expected = field_by_key()
    issues: list[TemplateIssue] = []
    for key in catalog_keys():
        if key not in texts:
            issues.append(TemplateIssue(key, "missing_key", "required text is missing"))
    for key in texts:
        if key not in expected:
            issues.append(TemplateIssue(str(key), "unknown_key", "text is not part of the catalog"))
    if issues:
        return tuple(issues)
    for key in catalog_keys():
        issues.extend(_validate_one(expected[key], texts[key]))
    return tuple(issues)


def render_customer_lines(texts: Mapping[str, str], messages: tuple[BotMessage, ...]) -> tuple[str, ...]:
    rendered = explain_messages(texts, messages)
    if isinstance(rendered, TemplateIssue):
        raise CustomerTextRenderError
    return rendered


def explain_messages(
    texts: Mapping[str, str],
    messages: tuple[BotMessage, ...],
) -> tuple[str, ...] | TemplateIssue:
    issues = validate_texts(texts)
    if issues:
        return issues[0]
    lines: list[str] = []
    for message in messages:
        rendered = _render_message(texts, message)
        if isinstance(rendered, TemplateIssue):
            return rendered
        lines.append(rendered)
    return tuple(lines)


def composed_main_menu(texts: Mapping[str, str]) -> str:
    lines = []
    for digit, service_id in MENU_ENTRIES:
        if service_for_menu_digit(digit) != service_id:
            raise CustomerTextRenderError
        title = str(texts.get(service_title_key(service_id)) or "").strip()
        lines.append(f"{digit}- {title}")
    return "\n".join(lines)


def dump_texts(texts: Mapping[str, str]) -> str:
    ordered = {key: str(texts[key]) for key in catalog_keys()}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def load_texts(payload: object) -> dict[str, str] | None:
    if not isinstance(payload, str) or not payload.strip():
        return None
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    parsed: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return None
        parsed[key] = value
    return parsed


def texts_match(left: Mapping[str, str], right: Mapping[str, str]) -> bool:
    if validate_texts(left) or validate_texts(right):
        return False
    return dump_texts(left) == dump_texts(right)


def _scan(template: str, allowed: frozenset[str]) -> TemplateIssue | None:
    cursor = 0
    while cursor < len(template):
        if template[cursor] == "}":
            return TemplateIssue("", "invalid_syntax", "unbalanced braces")
        if template[cursor] == "{" and cursor > 0 and template[cursor - 1] == "$":
            return TemplateIssue("", "invalid_syntax", "${")
        if template[cursor] != "{":
            nxt = template.find("{", cursor)
            if nxt < 0:
                return None
            cursor = nxt
            continue
        end = template.find("}", cursor + 1)
        if end < 0:
            return TemplateIssue("", "invalid_syntax", "unclosed placeholder")
        name = template[cursor + 1 : end]
        if _TOKEN.fullmatch(name) is None or name not in allowed:
            code = "unknown_variable" if _TOKEN.fullmatch(name) else "invalid_syntax"
            return TemplateIssue("", code, name)
        cursor = end + 1
    return None


def _validate_one(field: TemplateField, value: object) -> tuple[TemplateIssue, ...]:
    if not isinstance(value, str):
        return (TemplateIssue(field.key, "not_text", "text must be plain text"),)
    if _CONTROL.search(value):
        return (TemplateIssue(field.key, "invalid_characters", "text contains a control character"),)
    if not value.strip():
        return (TemplateIssue(field.key, "empty", "text is required"),)
    if len(value) > field.max_length:
        return (
            TemplateIssue(
                field.key,
                "too_long",
                f"text is longer than {field.max_length} characters",
            ),
        )
    scanned = _scan(value, field.variables)
    if isinstance(scanned, TemplateIssue):
        return (TemplateIssue(field.key, scanned.code, scanned.detail),)
    return ()


def _render_message(texts: Mapping[str, str], message: BotMessage) -> str | TemplateIssue:
    if message.key == BotMessageKey.MAIN_MENU:
        return composed_main_menu(texts)
    field = field_by_key().get(message.key)
    if field is None:
        return TemplateIssue(message.key, "unknown_key", "message is not in the catalog")
    values = dict(message.parameters)
    rendered = _substitute(str(texts[field.key]), field.variables, values, texts)
    if isinstance(rendered, TemplateIssue):
        return TemplateIssue(field.key, rendered.code, rendered.detail)
    return rendered


def _substitute(
    template: str,
    allowed: frozenset[str],
    values: Mapping[str, str],
    texts: Mapping[str, str],
) -> str | TemplateIssue:
    parts: list[str] = []
    cursor = 0
    while cursor < len(template):
        if template[cursor] == "}":
            return TemplateIssue("", "invalid_syntax", "unbalanced braces")
        if template[cursor] == "{" and cursor > 0 and template[cursor - 1] == "$":
            return TemplateIssue("", "invalid_syntax", "${")
        if template[cursor] != "{":
            nxt = template.find("{", cursor)
            if nxt < 0:
                parts.append(template[cursor:])
                break
            parts.append(template[cursor:nxt])
            cursor = nxt
            continue
        end = template.find("}", cursor + 1)
        if end < 0:
            return TemplateIssue("", "invalid_syntax", "unclosed placeholder")
        name = template[cursor + 1 : end]
        if _TOKEN.fullmatch(name) is None or name not in allowed:
            code = "unknown_variable" if _TOKEN.fullmatch(name) else "invalid_syntax"
            return TemplateIssue("", code, name)
        value = _placeholder_value(name, values, texts)
        if isinstance(value, TemplateIssue):
            return value
        parts.append(value)
        cursor = end + 1
    return "".join(parts)


def _placeholder_value(
    name: str,
    values: Mapping[str, str],
    texts: Mapping[str, str],
) -> str | TemplateIssue:
    raw = values.get(name, "")
    if name == "public_status":
        if raw not in _public_statuses():
            return TemplateIssue("", "unknown_variable", raw or name)
        return str(texts[status_label_key(raw)])
    if name == "service_id":
        known = {service_id for _digit, service_id in MENU_ENTRIES}
        if raw not in known:
            return TemplateIssue("", "unknown_variable", raw or name)
        return str(texts[service_title_key(raw)])
    return raw


def _public_statuses() -> tuple[str, ...]:
    return tuple(
        value
        for name, value in vars(PublicOrderStatus).items()
        if name.isupper() and isinstance(value, str)
    )


__all__ = [
    "GROUP_ORDER",
    "MAX_LABEL_LENGTH",
    "MAX_MESSAGE_LENGTH",
    "MENU_ENTRIES",
    "VARIABLE_NAMES",
    "CustomerTextRenderError",
    "TemplateField",
    "TemplateIssue",
    "catalog_keys",
    "composed_main_menu",
    "dump_texts",
    "explain_messages",
    "field_by_key",
    "load_texts",
    "render_customer_lines",
    "service_title_key",
    "status_label_key",
    "template_fields",
    "texts_match",
    "validate_texts",
]
