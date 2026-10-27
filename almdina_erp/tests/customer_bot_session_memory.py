"""In-memory session double for single-process tests.

Production protection is the MariaDB repository. This lock only keeps the
double consistent inside one test process.
"""

from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from almdina_erp.almdina_erp.application.customer_bot.reply_outbox import ClaimedReply
from almdina_erp.almdina_erp.application.customer_bot.session_store import BeginTurn
from almdina_erp.almdina_erp.domain.customer_bot.conversation import ConversationState
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    ABANDONED_CLAIM_REASON,
    ACCEPTED,
    CANCELLED,
    DEFAULT_REPLY_CLAIM_TTL,
    PART_DOCUMENT,
    CAPTION_TOO_LONG,
    PENDING,
    PROCESSING,
    REJECTED,
    UNKNOWN,
    ReplyIntent,
    blocks_later_reply,
    claim_is_abandoned,
    ordered_reply_intents,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import (
    CONFLICT,
    CONVERSATION_BUSY,
    DUPLICATE,
    IN_PROGRESS,
    LOST_LEASE,
    PROCESSED,
    PROCEED,
    SUPPRESSED,
    classify_stored_event,
    lease_is_active,
    utc_iso,
)


@dataclass
class _Conversation:
    revision: int
    state_json: str | None
    customer_id: str | None
    last_activity_on: str
    expires_on: str | None
    lease_token: str | None
    lease_expires_on: str | None


@dataclass
class _Event:
    fingerprint: str
    status: str
    outcome: str | None
    lease_token: str | None
    lease_expires_on: str | None
    completed_on: str | None


@dataclass
class _Reply:
    intent: ReplyIntent
    reply_id: str
    status: str
    attempt_count: int
    claim_token: str | None
    claimed_on: str | None
    provider_message_id: str | None
    reason_code: str | None
    created_on: datetime | None = None


class MemoryCustomerBotSessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.conversations: dict[tuple[str, str, str], _Conversation] = {}
        self.events: dict[tuple[str, str], _Event] = {}
        self.replies: dict[tuple[str, str, int], _Reply] = {}

    def note_terminal(self, *, connection_ref, provider_event_id, fingerprint, outcome, now) -> str:
        with self._lock:
            key = (connection_ref, provider_event_id)
            existing = self.events.get(key)
            now_iso = utc_iso(now)
            if existing is None:
                self.events[key] = _Event(fingerprint, "completed", outcome, None, None, now_iso)
                return outcome
            kind = classify_stored_event(
                status=existing.status,
                stored_fingerprint=existing.fingerprint,
                fingerprint=fingerprint,
                lease_token=existing.lease_token,
                lease_expires_on=existing.lease_expires_on,
                now_iso=now_iso,
            )
            return IN_PROGRESS if kind == "reclaim" else kind

    def begin_turn(
        self, *, connection_ref, conversation_id, sender_id, provider_event_id, fingerprint, now, lease_ttl
    ) -> BeginTurn:
        with self._lock:
            now_iso = utc_iso(now)
            lease_iso = utc_iso(now + lease_ttl)
            token = secrets.token_hex(16)
            conv_key = (connection_ref, conversation_id, sender_id)
            event_key = (connection_ref, provider_event_id)
            conversation = self.conversations.get(conv_key)
            event = self.events.get(event_key)
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
                conversation = _Conversation(1, None, None, now_iso, None, token, lease_iso)
                self.conversations[conv_key] = conversation
                created = True
            else:
                previous_token = conversation.lease_token
                previous_expires = conversation.lease_expires_on
                revision = conversation.revision
                state = _state_from(conversation.state_json)
                conversation.lease_token = token
                conversation.lease_expires_on = lease_iso
                conversation.last_activity_on = now_iso
            if event_kind == "reclaim" and event is not None:
                event.lease_token = token
                event.lease_expires_on = lease_iso
                return BeginTurn(PROCEED, revision, state, token, token)
            if event_key in self.events:
                self._unwind(conv_key, token, previous_token, previous_expires, created)
                raced = self.events[event_key]
                kind = classify_stored_event(
                    status=raced.status,
                    stored_fingerprint=raced.fingerprint,
                    fingerprint=fingerprint,
                    lease_token=raced.lease_token,
                    lease_expires_on=raced.lease_expires_on,
                    now_iso=now_iso,
                )
                return BeginTurn(IN_PROGRESS if kind == "reclaim" else kind)
            self.events[event_key] = _Event(fingerprint, "processing", None, token, lease_iso, None)
            return BeginTurn(PROCEED, revision, state, token, token)

    def complete_turn(
        self, *, connection_ref, conversation_id, sender_id, provider_event_id, fingerprint,
        conversation_token, event_token, revision, state, now, acceptance_unchanged, build_replies,
    ) -> str:
        with self._lock:
            conversation, event = self._owned(
                connection_ref, conversation_id, sender_id, provider_event_id, fingerprint,
                conversation_token, event_token, revision,
            )
            if conversation is None or event is None:
                return LOST_LEASE
            if not acceptance_unchanged():
                conversation.lease_token = None
                conversation.lease_expires_on = None
                event.status = "completed"
                event.outcome = SUPPRESSED
                event.lease_token = None
                event.lease_expires_on = None
                event.completed_on = utc_iso(now)
                return SUPPRESSED
            replies = ordered_reply_intents(tuple(build_replies()))
            if not self._finish(
                connection_ref, conversation_id, sender_id, provider_event_id, fingerprint,
                conversation_token, event_token, revision, state, now,
            ):
                return LOST_LEASE
            self._store_replies(replies, now=now)
            return PROCESSED

    def claim_next(
        self,
        *,
        now,
        eligible_phone: str | None = None,
        created_not_before: datetime | None = None,
    ) -> ClaimedReply | None:
        with self._lock:
            eligible = []
            for row in self.replies.values():
                if row.status != PENDING or self._blocked(row.intent):
                    continue
                if eligible_phone and row.intent.normalized_phone != eligible_phone:
                    continue
                if created_not_before is not None:
                    created = row.created_on
                    if created is None:
                        continue
                    stamp = created if created.tzinfo is not None else created.replace(tzinfo=now.tzinfo)
                    cutoff = (
                        created_not_before
                        if created_not_before.tzinfo is not None
                        else created_not_before.replace(tzinfo=now.tzinfo)
                    )
                    if stamp < cutoff:
                        continue
                eligible.append(row)
            if not eligible:
                return None
            eligible.sort(key=lambda row: (row.intent.sequence, row.reply_id))
            chosen = eligible[0]
            token = secrets.token_hex(16)
            chosen.status = PROCESSING
            chosen.attempt_count += 1
            chosen.claim_token = token
            chosen.claimed_on = utc_iso(now)
            intent = chosen.intent
            group_specs = tuple(
                item.intent.document_spec
                for item in self.replies.values()
                if item.intent.connection_ref == intent.connection_ref
                and item.intent.provider_event_id == intent.provider_event_id
                and item.intent.part_kind == PART_DOCUMENT
                and item.intent.document_spec is not None
            )
            return ClaimedReply(
                reply_id=chosen.reply_id,
                claim_token=token,
                connection_ref=intent.connection_ref,
                provider_event_id=intent.provider_event_id,
                conversation_id=intent.conversation_id,
                destination_id=intent.destination_id,
                sequence=intent.sequence,
                body=intent.body,
                attempt_count=chosen.attempt_count,
                part_kind=intent.part_kind,
                document_spec=intent.document_spec,
                customer_id=intent.customer_id,
                normalized_phone=intent.normalized_phone,
                acceptance_epoch=intent.acceptance_epoch,
                group_document_specs=group_specs,
                created_on=chosen.created_on,
                message_key=intent.message_key,
            )

    def record_result(self, *, reply_id, claim_token, result, now) -> bool:
        del now
        with self._lock:
            row = next((item for item in self.replies.values() if item.reply_id == reply_id), None)
            status = result.disposition.value
            if (
                row is None
                or row.status != PROCESSING
                or row.claim_token != claim_token
                or result.reply_id != reply_id
                or status not in {ACCEPTED, REJECTED, UNKNOWN}
            ):
                return False
            row.status = status
            if row.reason_code != CAPTION_TOO_LONG:
                row.reason_code = result.reason_code
            row.provider_message_id = result.provider_message_id if status == ACCEPTED else None
            return True

    def record_cancelled(self, *, reply_id, claim_token, reason_code, now) -> bool:
        del now
        with self._lock:
            row = next((item for item in self.replies.values() if item.reply_id == reply_id), None)
            if row is None or row.status != PROCESSING or row.claim_token != claim_token:
                return False
            row.status = CANCELLED
            row.reason_code = reason_code
            row.provider_message_id = None
            return True

    def recover_abandoned_claims(self, *, now, claim_ttl=DEFAULT_REPLY_CLAIM_TTL, limit=50) -> int:
        with self._lock:
            bounded = max(1, min(int(limit), 200))
            recovered = 0
            for row in self.replies.values():
                if recovered >= bounded:
                    break
                if row.status != PROCESSING or not row.claim_token:
                    continue
                if not claim_is_abandoned(row.claimed_on, now, claim_ttl):
                    continue
                row.status = UNKNOWN
                row.reason_code = ABANDONED_CLAIM_REASON
                row.provider_message_id = None
                recovered += 1
            return recovered

    def abort_turn(
        self, *, connection_ref, conversation_id, sender_id, provider_event_id,
        conversation_token, event_token, revision,
    ) -> bool:
        with self._lock:
            conv_key = (connection_ref, conversation_id, sender_id)
            event_key = (connection_ref, provider_event_id)
            conversation = self.conversations.get(conv_key)
            event = self.events.get(event_key)
            if (
                conversation is None
                or event is None
                or conversation.lease_token != conversation_token
                or conversation.revision != revision
                or event.lease_token != event_token
                or event.status != "processing"
            ):
                return False
            conversation.lease_token = None
            conversation.lease_expires_on = None
            del self.events[event_key]
            return True

    def purge(self, *, now, conversation_retention, event_retention, limit) -> tuple[int, int]:
        with self._lock:
            bounded = max(1, min(int(limit), 200))
            now_iso = utc_iso(now)
            conversation_cutoff = utc_iso(now - conversation_retention)
            event_cutoff = utc_iso(now - event_retention)
            removed_conversations = 0
            for key, row in list(self.conversations.items()):
                if removed_conversations >= bounded:
                    break
                leased = lease_is_active(row.lease_token, row.lease_expires_on, now_iso)
                expired = (row.expires_on is not None and row.expires_on < conversation_cutoff) or (
                    row.state_json is None and row.last_activity_on < conversation_cutoff
                )
                if not leased and expired:
                    del self.conversations[key]
                    removed_conversations += 1
            removed_events = 0
            for key, row in list(self.events.items()):
                if removed_events >= bounded:
                    break
                if row.status == "completed" and row.completed_on and row.completed_on < event_cutoff:
                    del self.events[key]
                    removed_events += 1
            return removed_conversations, removed_events

    def steal_lease(self, connection_ref: str, conversation_id: str, sender_id: str) -> None:
        with self._lock:
            row = self.conversations[(connection_ref, conversation_id, sender_id)]
            row.lease_token = "stolen"
            row.lease_expires_on = "9999-01-01T00:00:00+00:00"

    def _finish(
        self, connection_ref, conversation_id, sender_id, provider_event_id, fingerprint,
        conversation_token, event_token, revision, state, now,
    ) -> bool:
        conversation, event = self._owned(
            connection_ref, conversation_id, sender_id, provider_event_id, fingerprint,
            conversation_token, event_token, revision,
        )
        if conversation is None or event is None:
            return False
        if state is None:
            conversation.state_json = None
            conversation.customer_id = None
            conversation.expires_on = utc_iso(now)
        else:
            payload = state.to_payload()
            conversation.state_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            conversation.customer_id = state.customer_id
            conversation.expires_on = utc_iso(state.expires_at)
        conversation.revision += 1
        conversation.last_activity_on = utc_iso(now)
        conversation.lease_token = None
        conversation.lease_expires_on = None
        event.status = "completed"
        event.outcome = "processed"
        event.lease_token = None
        event.lease_expires_on = None
        event.completed_on = utc_iso(now)
        return True

    def _store_replies(
        self,
        replies: tuple[ReplyIntent, ...],
        *,
        now: datetime | None = None,
    ) -> None:
        created = now if now is not None else datetime.now(timezone.utc)
        for intent in replies:
            key = (intent.connection_ref, intent.provider_event_id, intent.sequence)
            if key in self.replies:
                raise RuntimeError("reply intent already stored for this event")
            self.replies[key] = _Reply(
                intent,
                intent.reply_id(),
                PENDING,
                0,
                None,
                None,
                None,
                intent.reason_code,
                created_on=created,
            )

    def _blocked(self, intent: ReplyIntent) -> bool:
        for row in self.replies.values():
            earlier = row.intent
            if (
                earlier.connection_ref == intent.connection_ref
                and earlier.provider_event_id == intent.provider_event_id
                and earlier.sequence < intent.sequence
                and blocks_later_reply(row.status)
            ):
                return True
        return False

    def _owned(
        self, connection_ref, conversation_id, sender_id, provider_event_id, fingerprint,
        conversation_token, event_token, revision,
    ):
        conversation = self.conversations.get((connection_ref, conversation_id, sender_id))
        event = self.events.get((connection_ref, provider_event_id))
        if (
            conversation is None
            or event is None
            or conversation.lease_token != conversation_token
            or conversation.revision != revision
            or event.lease_token != event_token
            or event.fingerprint != fingerprint
            or event.status != "processing"
        ):
            return None, None
        return conversation, event

    def _unwind(self, conv_key, token, previous_token, previous_expires, created: bool) -> None:
        row = self.conversations.get(conv_key)
        if row is None or row.lease_token != token:
            return
        if created:
            del self.conversations[conv_key]
            return
        row.lease_token = previous_token
        row.lease_expires_on = previous_expires


def _state_from(payload: str | None) -> ConversationState | None:
    if not payload:
        return None
    from almdina_erp.almdina_erp.domain.customer_bot.conversation import conversation_state_from_payload

    try:
        return conversation_state_from_payload(json.loads(payload))
    except json.JSONDecodeError:
        return None
