"""Employee endpoints for customer-bot texts, preview, and the on/off switch.

The session user is the only actor. Guest access is closed. These endpoints
do not send WhatsApp messages, open a session, or read a customer document.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.customer_bot.preview_conversation import (
    PREVIEW_SCENARIOS,
    preview_clock,
    preview_customer_bot_turn,
)
from almdina_erp.almdina_erp.application.customer_bot.settings_commands import (
    CustomerBotSettingsConflict,
    CustomerBotSettingsInvalid,
    CustomerBotSettingsMissing,
    publish_customer_bot_texts as publish_stored_texts,
    save_customer_bot_draft as save_stored_draft,
    set_customer_bot_enabled as set_stored_enabled,
)
from almdina_erp.almdina_erp.domain.customer_bot.message_defaults import variable_examples
from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
    VARIABLE_NAMES,
    TemplateIssue,
    template_fields,
    texts_match,
    validate_texts,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_repository import (
    FrappeCustomerBotSettingsRepository,
)


_MAX_PAYLOAD = 100_000


@frappe.whitelist(methods=["POST"])
def get_customer_bot_settings() -> dict[str, Any]:
    _authorize()
    try:
        return _snapshot_payload(_store().load())
    except CustomerBotSettingsMissing:
        return _failure("missing")


@frappe.whitelist(methods=["POST"])
def save_customer_bot_draft(expected_revision: object, texts: object) -> dict[str, Any]:
    _authorize()
    try:
        saved = save_stored_draft(
            _store(),
            _texts(texts),
            _revision(expected_revision),
            _actor(),
            frappe.utils.now(),
        )
    except CustomerBotSettingsInvalid as error:
        return _failure("invalid_texts", error.issues)
    except CustomerBotSettingsConflict:
        return _failure("conflict")
    except CustomerBotSettingsMissing:
        return _failure("missing")
    return _snapshot_payload(saved)


@frappe.whitelist(methods=["POST"])
def publish_customer_bot_texts(expected_revision: object, texts: object) -> dict[str, Any]:
    _authorize()
    try:
        saved = publish_stored_texts(
            _store(),
            _texts(texts),
            _revision(expected_revision),
            _actor(),
            frappe.utils.now(),
        )
    except CustomerBotSettingsInvalid as error:
        return _failure("invalid_texts", error.issues)
    except CustomerBotSettingsConflict:
        return _failure("conflict")
    except CustomerBotSettingsMissing:
        return _failure("missing")
    return _snapshot_payload(saved)


@frappe.whitelist(methods=["POST"])
def set_customer_bot_enabled(expected_revision: object, enabled: object) -> dict[str, Any]:
    _authorize()
    try:
        saved = set_stored_enabled(
            _store(),
            _enabled(enabled),
            _revision(expected_revision),
            _actor(),
            frappe.utils.now(),
        )
    except CustomerBotSettingsInvalid as error:
        return _failure("invalid_texts", error.issues)
    except CustomerBotSettingsConflict:
        return _failure("conflict")
    except CustomerBotSettingsMissing:
        return _failure("missing")
    return _snapshot_payload(saved)


@frappe.whitelist(methods=["POST"])
def preview_customer_bot(
    source: object,
    scenario: object,
    text: object,
    state: object = None,
    texts: object = None,
) -> dict[str, Any]:
    _authorize()
    try:
        chosen = _preview_texts(source, texts)
        preview_state = _state(state)
    except CustomerBotSettingsInvalid as error:
        return _failure("invalid_texts", error.issues)
    except CustomerBotSettingsMissing:
        return _failure("missing")
    if isinstance(chosen, dict) and chosen.get("ok") is False:
        return chosen
    result = preview_customer_bot_turn(
        chosen,
        str(scenario or ""),
        text if isinstance(text, str) else "",
        preview_state,
        preview_clock(),
    )
    return {
        "ok": result.ok,
        "code": result.code,
        "lines": list(result.lines),
        "state": result.state,
        "issues": [_issue(issue) for issue in result.issues],
    }


def _authorize() -> None:
    if frappe.session.user in (None, "", "Guest"):
        frappe.throw(_("You do not have permission for this action."), frappe.PermissionError)
    require_doctype_capability(Capability.MANAGE_CUSTOMER_BOT_SETTINGS)


def _store() -> FrappeCustomerBotSettingsRepository:
    return FrappeCustomerBotSettingsRepository()


def _actor() -> str:
    return str(frappe.session.user)


def _preview_texts(source: object, texts: object) -> Mapping[str, str] | dict[str, Any]:
    if source == "published":
        return _store().load().published
    if source == "draft":
        return _texts(texts)
    return _failure("invalid_source")


def _snapshot_payload(snapshot: CustomerBotSettingsSnapshot) -> dict[str, Any]:
    return {
        "ok": True,
        "code": "ok",
        "enabled": snapshot.enabled,
        "revision": snapshot.revision,
        "draft": snapshot.draft,
        "published": snapshot.published,
        "unpublished": not texts_match(snapshot.draft, snapshot.published),
        "draft_valid": not validate_texts(snapshot.draft),
        "published_valid": not validate_texts(snapshot.published),
        "published_on": snapshot.published_on,
        "published_by": snapshot.published_by,
        "modified": snapshot.modified,
        "modified_by": snapshot.modified_by,
        "fields": _fields(),
        "scenarios": list(PREVIEW_SCENARIOS),
        "issues": [],
    }


def _failure(code: str, issues: tuple[TemplateIssue, ...] = ()) -> dict[str, Any]:
    return {
        "ok": False,
        "code": code,
        "issues": [_issue(issue) for issue in issues],
    }


def _issue(issue: TemplateIssue) -> dict[str, str]:
    return {"key": issue.key, "code": issue.code, "detail": issue.detail}


def _fields() -> list[dict[str, Any]]:
    examples = variable_examples()
    return [
        {
            "key": field.key,
            "group": field.group,
            "max_length": field.max_length,
            "variables": [
                {"name": name, "example": examples[name]}
                for name in VARIABLE_NAMES
                if name in field.variables
            ],
        }
        for field in template_fields()
    ]


def _texts(payload: object) -> dict[str, str]:
    data = _object(payload)
    parsed: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise CustomerBotSettingsInvalid(
                (TemplateIssue(str(key), "not_text", "text must be plain text"),)
            )
        parsed[key] = value
    return parsed


def _state(payload: object) -> object:
    if payload in (None, "", "null"):
        return None
    return _object(payload)


def _object(payload: object) -> dict[str, Any]:
    if isinstance(payload, str):
        if len(payload) > _MAX_PAYLOAD:
            raise CustomerBotSettingsInvalid(
                (TemplateIssue("", "too_long", "payload is too large"),)
            )
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as error:
            raise CustomerBotSettingsInvalid(
                (TemplateIssue("", "invalid_syntax", "payload is not valid JSON"),)
            ) from error
    if not isinstance(payload, Mapping):
        raise CustomerBotSettingsInvalid(
            (TemplateIssue("", "not_text", "payload must be an object"),)
        )
    return dict(payload)


def _revision(value: object) -> int:
    if isinstance(value, bool):
        raise CustomerBotSettingsInvalid(
            (TemplateIssue("revision", "not_text", "revision must be an integer"),)
        )
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise CustomerBotSettingsInvalid(
        (TemplateIssue("revision", "not_text", "revision must be an integer"),)
    )


def _enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if value in ("0", "1"):
        return value == "1"
    raise CustomerBotSettingsInvalid(
        (TemplateIssue("enabled", "not_text", "enabled must be true or false"),)
    )
