"""MariaDB adapter for customer-bot sessions.

Each public method commits or rolls back before it returns, so a PDF render
never runs while a row lock is held. Completion of the session and the event
is one transaction. An old lease token cannot update either row after a newer
token has been stored.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta

import frappe
from almdina_erp.almdina_erp.application.customer_bot.session_store import BeginTurn
from almdina_erp.almdina_erp.domain.customer_bot.conversation import (
    ConversationState,
    conversation_state_from_payload,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    CONFLICT,
    CONVERSATION_BUSY,
    DUPLICATE,
    IN_PROGRESS,
    LOST_LEASE,
    PROCEED,
    PROCESSED,
    SUPPRESSED,
    classify_stored_event,
    lease_is_active,
    utc_iso,
)

from .customer_bot_session_records import CONVERSATION_DOCTYPE, EVENT_DOCTYPE

_CONVERSATION = f"tab{CONVERSATION_DOCTYPE}"
_EVENT = f"tab{EVENT_DOCTYPE}"
_MAX_PURGE = 200


class _Unowned(Exception):
    """The conditional write matched no row, so the transaction must roll back."""


class FrappeCustomerBotSessionRepository:
    def note_terminal(
        self,
        *,
        connection_ref: str,
        provider_event_id: str,
        fingerprint: str,
        outcome: str,
        now: datetime,
    ) -> str:
        return self._commit(lambda: self._note_terminal(
            connection_ref, provider_event_id, fingerprint, outcome, now
        ))

    def begin_turn(
        self,
        *,
        connection_ref: str,
        conversation_id: str,
        sender_id: str,
        provider_event_id: str,
        fingerprint: str,
        now: datetime,
        lease_ttl: timedelta,
    ) -> BeginTurn:
        return self._commit(lambda: self._begin_turn(
            connection_ref,
            conversation_id,
            sender_id,
            provider_event_id,
            fingerprint,
            now,
            lease_ttl,
        ))

    def complete_turn(
        self,
        *,
        connection_ref: str,
        conversation_id: str,
        sender_id: str,
        provider_event_id: str,
        fingerprint: str,
        conversation_token: str,
        event_token: str,
        revision: int,
        state: ConversationState | None,
        now: datetime,
        acceptance_unchanged,
    ) -> str:
        return self._commit_outcome(lambda: self._complete_turn(
            connection_ref,
            conversation_id,
            sender_id,
            provider_event_id,
            fingerprint,
            conversation_token,
            event_token,
            revision,
            state,
            now,
            acceptance_unchanged,
        ))

    def abort_turn(
        self,
        *,
        connection_ref: str,
        conversation_id: str,
        sender_id: str,
        provider_event_id: str,
        conversation_token: str,
        event_token: str,
        revision: int,
    ) -> bool:
        return self._commit_owned(lambda: self._abort_turn(
            connection_ref,
            conversation_id,
            sender_id,
            provider_event_id,
            conversation_token,
            event_token,
            revision,
        ))

    def purge(
        self,
        *,
        now: datetime,
        conversation_retention: timedelta,
        event_retention: timedelta,
        limit: int,
    ) -> tuple[int, int]:
        bounded = max(1, min(int(limit), _MAX_PURGE))
        return self._commit(lambda: self._purge(now, conversation_retention, event_retention, bounded))

    def _commit(self, work):
        try:
            result = work()
        except Exception:
            frappe.db.rollback()
            raise
        frappe.db.commit()
        return result

    def _commit_owned(self, work) -> bool:
        try:
            work()
        except _Unowned:
            frappe.db.rollback()
            return False
        except Exception:
            frappe.db.rollback()
            raise
        frappe.db.commit()
        return True

    def _note_terminal(self, connection_ref, provider_event_id, fingerprint, outcome, now) -> str:
        stamp = _modified()
        now_iso = utc_iso(now)
        try:
            _insert_event(
                connection_ref,
                provider_event_id,
                fingerprint,
                "completed",
                outcome,
                None,
                None,
                now_iso,
                stamp,
            )
            return outcome
        except Exception as exc:
            if not _is_duplicate(exc):
                raise
        event = _lock_event(connection_ref, provider_event_id)
        if event is None:
            raise RuntimeError("customer bot event disappeared after a duplicate insert")
        kind = classify_stored_event(
            status=event.status,
            stored_fingerprint=event.fingerprint,
            fingerprint=fingerprint,
            lease_token=event.lease_token,
            lease_expires_on=event.lease_expires_on,
            now_iso=now_iso,
        )
        if kind == "reclaim":
            return IN_PROGRESS
        return kind

    def _begin_turn(
        self,
        connection_ref,
        conversation_id,
        sender_id,
        provider_event_id,
        fingerprint,
        now,
        lease_ttl,
    ) -> BeginTurn:
        now_iso = utc_iso(now)
        lease_iso = utc_iso(now + lease_ttl)
        token = secrets.token_hex(16)
        conversation = _lock_conversation(connection_ref, conversation_id, sender_id)
        event = _lock_event(connection_ref, provider_event_id)
        event_kind = None
        if event is not None:
            event_kind = classify_stored_event(
                status=event.status,
                stored_fingerprint=event.fingerprint,
                fingerprint=fingerprint,
                lease_token=event.lease_token,
                lease_expires_on=event.lease_expires_on,
                now_iso=now_iso,
            )
        busy = conversation is not None and lease_is_active(
            conversation.lease_token, conversation.lease_expires_on, now_iso
        )
        if busy:
            if event_kind in {CONFLICT, DUPLICATE, IN_PROGRESS}:
                return BeginTurn(event_kind)
            if event_kind == "reclaim":
                return BeginTurn(IN_PROGRESS)
            return BeginTurn(CONVERSATION_BUSY)
        if event_kind in {CONFLICT, DUPLICATE, IN_PROGRESS}:
            return BeginTurn(event_kind)
        created = False
        previous_token = None
        previous_expires = None
        revision = 1
        state = None
        if conversation is None:
            try:
                _insert_conversation(
                    connection_ref, conversation_id, sender_id, token, lease_iso, now_iso, _modified()
                )
            except Exception as exc:
                if not _is_duplicate(exc):
                    raise
                return BeginTurn(CONVERSATION_BUSY)
            created = True
            conversation = _lock_conversation(connection_ref, conversation_id, sender_id)
        else:
            previous_token = conversation.lease_token
            previous_expires = conversation.lease_expires_on
            revision = int(conversation.revision)
            state = _state_from(conversation.state_json)
            if _affected(
                f"""update `{_CONVERSATION}`
                    set lease_token=%s, lease_expires_on=%s, last_activity_on=%s, modified=%s
                    where name=%s and revision=%s
                      and (lease_token is null or lease_token='' or lease_expires_on is null or lease_expires_on<=%s)""",
                (token, lease_iso, now_iso, _modified(), conversation.name, revision, now_iso),
            ) != 1:
                return BeginTurn(CONVERSATION_BUSY)
        if event_kind == "reclaim":
            if _affected(
                f"""update `{_EVENT}`
                    set lease_token=%s, lease_expires_on=%s, modified=%s
                    where name=%s and fingerprint=%s and status='processing'
                      and (lease_expires_on is null or lease_expires_on<=%s)""",
                (token, lease_iso, _modified(), event.name, fingerprint, now_iso),
            ) != 1:
                _unwind(conversation.name, token, previous_token, previous_expires, created)
                return BeginTurn(IN_PROGRESS)
            return BeginTurn(PROCEED, revision, state, token, token)
        try:
            _insert_event(
                connection_ref,
                provider_event_id,
                fingerprint,
                "processing",
                None,
                token,
                lease_iso,
                None,
                _modified(),
            )
        except Exception as exc:
            if not _is_duplicate(exc):
                raise
            _unwind(conversation.name, token, previous_token, previous_expires, created)
            raced = _lock_event(connection_ref, provider_event_id)
            if raced is None:
                return BeginTurn(IN_PROGRESS)
            kind = classify_stored_event(
                status=raced.status,
                stored_fingerprint=raced.fingerprint,
                fingerprint=fingerprint,
                lease_token=raced.lease_token,
                lease_expires_on=raced.lease_expires_on,
                now_iso=now_iso,
            )
            return BeginTurn(IN_PROGRESS if kind == "reclaim" else kind)
        return BeginTurn(PROCEED, revision, state, token, token)

    def _commit_outcome(self, work) -> str:
        try:
            result = work()
        except _Unowned:
            frappe.db.rollback()
            return LOST_LEASE
        except Exception:
            frappe.db.rollback()
            raise
        frappe.db.commit()
        return result

    def _complete_turn(
        self,
        connection_ref,
        conversation_id,
        sender_id,
        provider_event_id,
        fingerprint,
        conversation_token,
        event_token,
        revision,
        state,
        now,
        acceptance_unchanged,
    ) -> str:
        _require_conversation(
            connection_ref, conversation_id, sender_id, conversation_token, revision
        )
        _require_event(connection_ref, provider_event_id, event_token, fingerprint)
        if not acceptance_unchanged():
            self._suppress_turn(
                connection_ref,
                conversation_id,
                sender_id,
                provider_event_id,
                fingerprint,
                conversation_token,
                event_token,
                revision,
                now,
            )
            return SUPPRESSED
        self._finish_turn(
            connection_ref,
            conversation_id,
            sender_id,
            provider_event_id,
            fingerprint,
            conversation_token,
            event_token,
            revision,
            state,
            now,
        )
        return PROCESSED

    def _finish_turn(
        self,
        connection_ref,
        conversation_id,
        sender_id,
        provider_event_id,
        fingerprint,
        conversation_token,
        event_token,
        revision,
        state,
        now,
    ) -> None:
        conversation = _require_conversation(
            connection_ref, conversation_id, sender_id, conversation_token, revision
        )
        event = _require_event(connection_ref, provider_event_id, event_token, fingerprint)
        payload, customer_id, expires_on = _stored_state(state, now)
        if _affected(
            f"""update `{_CONVERSATION}`
                set state_json=%s, customer_id=%s, revision=revision+1,
                    last_activity_on=%s, expires_on=%s, lease_token=null, lease_expires_on=null, modified=%s
                where name=%s and lease_token=%s and revision=%s""",
            (payload, customer_id, utc_iso(now), expires_on, _modified(), conversation.name, conversation_token, revision),
        ) != 1:
            raise _Unowned
        if _affected(
            f"""update `{_EVENT}`
                set status='completed', outcome='processed', lease_token=null, lease_expires_on=null,
                    completed_on=%s, modified=%s
                where name=%s and lease_token=%s and fingerprint=%s and status='processing'""",
            (utc_iso(now), _modified(), event.name, event_token, fingerprint),
        ) != 1:
            raise _Unowned

    def _suppress_turn(
        self,
        connection_ref,
        conversation_id,
        sender_id,
        provider_event_id,
        fingerprint,
        conversation_token,
        event_token,
        revision,
        now,
    ) -> None:
        conversation = _require_conversation(
            connection_ref, conversation_id, sender_id, conversation_token, revision
        )
        event = _require_event(connection_ref, provider_event_id, event_token, fingerprint)
        if _affected(
            f"""update `{_CONVERSATION}`
                set lease_token=null, lease_expires_on=null, modified=%s
                where name=%s and lease_token=%s and revision=%s""",
            (_modified(), conversation.name, conversation_token, revision),
        ) != 1:
            raise _Unowned
        if _affected(
            f"""update `{_EVENT}`
                set status='completed', outcome='suppressed', lease_token=null, lease_expires_on=null,
                    completed_on=%s, modified=%s
                where name=%s and lease_token=%s and fingerprint=%s and status='processing'""",
            (utc_iso(now), _modified(), event.name, event_token, fingerprint),
        ) != 1:
            raise _Unowned

    def _abort_turn(
        self,
        connection_ref,
        conversation_id,
        sender_id,
        provider_event_id,
        conversation_token,
        event_token,
        revision,
    ) -> None:
        conversation = _require_conversation(
            connection_ref, conversation_id, sender_id, conversation_token, revision
        )
        event = _lock_event(connection_ref, provider_event_id)
        if (
            event is None
            or event.lease_token != event_token
            or event.status != "processing"
        ):
            raise _Unowned
        if _affected(
            f"""update `{_CONVERSATION}`
                set lease_token=null, lease_expires_on=null, modified=%s
                where name=%s and lease_token=%s and revision=%s""",
            (_modified(), conversation.name, conversation_token, revision),
        ) != 1:
            raise _Unowned
        if _affected(
            f"delete from `{_EVENT}` where name=%s and lease_token=%s and status='processing'",
            (event.name, event_token),
        ) != 1:
            raise _Unowned

    def _purge(self, now, conversation_retention, event_retention, limit) -> tuple[int, int]:
        now_iso = utc_iso(now)
        conversation_cutoff = utc_iso(now - conversation_retention)
        event_cutoff = utc_iso(now - event_retention)
        conversations = _affected(
            f"""delete from `{_CONVERSATION}`
                where name in (
                    select name from (
                        select name from `{_CONVERSATION}`
                        where (lease_token is null or lease_token='' or lease_expires_on is null or lease_expires_on<=%s)
                          and (
                            (expires_on is not null and expires_on<%s)
                            or (state_json is null and last_activity_on<%s)
                          )
                        order by last_activity_on asc
                        limit %s
                    ) as expired_sessions
                )""",
            (now_iso, conversation_cutoff, conversation_cutoff, limit),
        )
        events = _affected(
            f"""delete from `{_EVENT}`
                where name in (
                    select name from (
                        select name from `{_EVENT}`
                        where status='completed' and completed_on is not null and completed_on<%s
                        order by completed_on asc
                        limit %s
                    ) as expired_events
                )""",
            (event_cutoff, limit),
        )
        return conversations, events


def _require_conversation(connection_ref, conversation_id, sender_id, token, revision):
    conversation = _lock_conversation(connection_ref, conversation_id, sender_id)
    if (
        conversation is None
        or conversation.lease_token != token
        or int(conversation.revision) != int(revision)
    ):
        raise _Unowned
    return conversation


def _require_event(connection_ref, provider_event_id, token, fingerprint):
    event = _lock_event(connection_ref, provider_event_id)
    if (
        event is None
        or event.lease_token != token
        or event.fingerprint != fingerprint
        or event.status != "processing"
    ):
        raise _Unowned
    return event


def _lock_conversation(connection_ref, conversation_id, sender_id):
    rows = frappe.db.sql(
        f"""select name, revision, state_json, customer_id, lease_token, lease_expires_on
            from `{_CONVERSATION}`
            where connection_ref=%s and conversation_id=%s and sender_id=%s
            for update""",
        (connection_ref, conversation_id, sender_id),
        as_dict=True,
    )
    return rows[0] if rows else None


def _lock_event(connection_ref, provider_event_id):
    rows = frappe.db.sql(
        f"""select name, fingerprint, status, outcome, lease_token, lease_expires_on
            from `{_EVENT}`
            where connection_ref=%s and provider_event_id=%s
            for update""",
        (connection_ref, provider_event_id),
        as_dict=True,
    )
    return rows[0] if rows else None


def _insert_conversation(connection_ref, conversation_id, sender_id, token, lease_iso, now_iso, stamp) -> None:
    frappe.db.sql(
        f"""insert into `{_CONVERSATION}`
            (name, creation, modified, modified_by, owner, docstatus,
             connection_ref, conversation_id, sender_id, state_json, customer_id, revision,
             last_activity_on, expires_on, lease_token, lease_expires_on)
            values (%s, %s, %s, 'Administrator', 'Administrator', 0,
                    %s, %s, %s, null, null, 1, %s, null, %s, %s)""",
        (frappe.generate_hash(length=12), stamp, stamp, connection_ref, conversation_id, sender_id, now_iso, token, lease_iso),
    )


def _insert_event(
    connection_ref,
    provider_event_id,
    fingerprint,
    status,
    outcome,
    token,
    lease_iso,
    completed_on,
    stamp,
) -> None:
    frappe.db.sql(
        f"""insert into `{_EVENT}`
            (name, creation, modified, modified_by, owner, docstatus,
             connection_ref, provider_event_id, fingerprint, status, outcome,
             lease_token, lease_expires_on, completed_on)
            values (%s, %s, %s, 'Administrator', 'Administrator', 0,
                    %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            frappe.generate_hash(length=12),
            stamp,
            stamp,
            connection_ref,
            provider_event_id,
            fingerprint,
            status,
            outcome,
            token,
            lease_iso,
            completed_on,
        ),
    )


def _unwind(name, token, previous_token, previous_expires, created: bool) -> None:
    if created:
        frappe.db.sql(
            f"delete from `{_CONVERSATION}` where name=%s and lease_token=%s and state_json is null",
            (name, token),
        )
        return
    frappe.db.sql(
        f"""update `{_CONVERSATION}`
            set lease_token=%s, lease_expires_on=%s
            where name=%s and lease_token=%s""",
        (previous_token, previous_expires, name, token),
    )


def _stored_state(state: ConversationState | None, now: datetime) -> tuple[str | None, str | None, str]:
    if state is None:
        return None, None, utc_iso(now)
    payload = state.to_payload()
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True), state.customer_id, utc_iso(state.expires_at)


def _state_from(payload: str | None) -> ConversationState | None:
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return conversation_state_from_payload(parsed)


def _affected(query: str, values: tuple) -> int:
    frappe.db.sql(query, values)
    row = frappe.db.sql("select row_count()")
    return int(row[0][0]) if row else 0


def _modified() -> str:
    return frappe.utils.now()


def _is_duplicate(exc: Exception) -> bool:
    return bool(exc.args) and exc.args[0] == 1062


__all__ = ["FrappeCustomerBotSessionRepository"]
