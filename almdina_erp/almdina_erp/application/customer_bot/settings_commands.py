"""Save, publish, and switch the customer bot without rendering a reply.

Draft writes do not change the published copy. Publish validates every text
and replaces that copy in one store call. It does not turn the bot on.
Turning the bot on requires a valid published copy. Turning it off does not
read the draft.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from almdina_erp.almdina_erp.domain.customer_bot.message_templates import (
    TemplateIssue,
    validate_texts,
)


@dataclass(frozen=True, slots=True)
class CustomerBotSettingsSnapshot:
    enabled: bool
    revision: int
    draft: dict[str, str]
    published: dict[str, str]
    published_on: str | None
    published_by: str | None
    modified: str | None
    modified_by: str | None


class CustomerBotSettingsMissing(Exception):
    def __str__(self) -> str:
        return "Customer bot settings are not installed."


class CustomerBotSettingsConflict(Exception):
    def __str__(self) -> str:
        return "Customer bot settings were changed by someone else."


class CustomerBotSettingsInvalid(Exception):
    def __init__(self, issues: tuple[TemplateIssue, ...]) -> None:
        self.issues = issues
        super().__init__("Customer bot texts are invalid.")


class CustomerBotSettingsStore(Protocol):
    def load(self) -> CustomerBotSettingsSnapshot: ...

    def save_draft(
        self,
        texts: Mapping[str, str],
        expected_revision: int,
        actor: str,
        modified: str,
    ) -> CustomerBotSettingsSnapshot | None: ...

    def publish(
        self,
        texts: Mapping[str, str],
        expected_revision: int,
        actor: str,
        modified: str,
    ) -> CustomerBotSettingsSnapshot | None: ...

    def set_enabled(
        self,
        enabled: bool,
        expected_revision: int,
        actor: str,
        modified: str,
    ) -> CustomerBotSettingsSnapshot | None: ...


def save_customer_bot_draft(
    store: CustomerBotSettingsStore,
    texts: Mapping[str, str],
    expected_revision: int,
    actor: str,
    modified: str,
) -> CustomerBotSettingsSnapshot:
    _require_revision(expected_revision)
    _require_actor(actor, modified)
    issues = validate_texts(texts)
    if issues:
        raise CustomerBotSettingsInvalid(issues)
    saved = store.save_draft(dict(texts), expected_revision, actor, modified)
    if saved is None:
        raise CustomerBotSettingsConflict
    return saved


def publish_customer_bot_texts(
    store: CustomerBotSettingsStore,
    texts: Mapping[str, str],
    expected_revision: int,
    actor: str,
    modified: str,
) -> CustomerBotSettingsSnapshot:
    _require_revision(expected_revision)
    _require_actor(actor, modified)
    issues = validate_texts(texts)
    if issues:
        raise CustomerBotSettingsInvalid(issues)
    saved = store.publish(dict(texts), expected_revision, actor, modified)
    if saved is None:
        raise CustomerBotSettingsConflict
    return saved


def set_customer_bot_enabled(
    store: CustomerBotSettingsStore,
    enabled: bool,
    expected_revision: int,
    actor: str,
    modified: str,
) -> CustomerBotSettingsSnapshot:
    _require_revision(expected_revision)
    _require_actor(actor, modified)
    if not isinstance(enabled, bool):
        raise CustomerBotSettingsInvalid(
            (TemplateIssue("enabled", "not_text", "enabled must be true or false"),)
        )
    if enabled:
        current = store.load()
        issues = validate_texts(current.published)
        if issues:
            raise CustomerBotSettingsInvalid(issues)
    saved = store.set_enabled(enabled, expected_revision, actor, modified)
    if saved is None:
        raise CustomerBotSettingsConflict
    return saved


def _require_revision(expected_revision: int) -> None:
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise CustomerBotSettingsInvalid(
            (TemplateIssue("revision", "not_text", "revision must be an integer"),)
        )
    if expected_revision < 1:
        raise CustomerBotSettingsInvalid(
            (TemplateIssue("revision", "invalid_syntax", "revision is missing"),)
        )


def _require_actor(actor: str, modified: str) -> None:
    if not isinstance(actor, str) or not actor.strip() or actor == "Guest":
        raise CustomerBotSettingsInvalid(
            (TemplateIssue("actor", "empty", "an employee session is required"),)
        )
    if not isinstance(modified, str) or not modified.strip():
        raise CustomerBotSettingsInvalid(
            (TemplateIssue("modified", "empty", "a modification time is required"),)
        )


__all__ = [
    "CustomerBotSettingsConflict",
    "CustomerBotSettingsMissing",
    "CustomerBotSettingsInvalid",
    "CustomerBotSettingsSnapshot",
    "CustomerBotSettingsStore",
    "publish_customer_bot_texts",
    "save_customer_bot_draft",
    "set_customer_bot_enabled",
]
