"""Claim and finish customer-bot reply intents.

The inbound commit inserts the rows. This adapter only moves a pending row to
processing, stores the gateway result for that same claim, marks a preflight
cancel, or marks an expired claim ``unknown``. It does not call the gateway.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import frappe

from almdina_erp.almdina_erp.application.customer_bot.reply_outbox import ClaimedReply
from almdina_erp.almdina_erp.domain.customer_bot.document_reply_spec import (
    document_reply_spec_from_payload,
)
from almdina_erp.almdina_erp.domain.customer_bot.reply_intent import (
    ABANDONED_CLAIM_REASON,
    ACCEPTED,
    CANCELLED,
    DEFAULT_REPLY_CLAIM_TTL,
    PART_TEXT,
    PROCESSING,
    REJECTED,
    UNKNOWN,
    claim_is_abandoned,
)
from almdina_erp.almdina_erp.domain.customer_bot.session_admission import utc_iso
from almdina_erp.almdina_erp.domain.customer_bot.text_reply import TextSendResult

from .customer_bot_session_records import REPLY_DOCTYPE
from .customer_bot_session_repository import _commit_with_deadlock_retry

_REPLY = f"tab{REPLY_DOCTYPE}"
_TERMINAL = {ACCEPTED, REJECTED, UNKNOWN}


class FrappeCustomerBotReplyRepository:
    def claim_next(
        self,
        *,
        now: datetime,
        eligible_phone: str | None = None,
        created_not_before: datetime | None = None,
    ) -> ClaimedReply | None:
        return _commit_with_deadlock_retry(
            lambda: self._claim(
                now,
                eligible_phone=eligible_phone,
                created_not_before=created_not_before,
            )
        )

    def record_result(
        self,
        *,
        reply_id: str,
        claim_token: str,
        result: TextSendResult,
        now: datetime,
    ) -> bool:
        return _commit_with_deadlock_retry(lambda: self._record(reply_id, claim_token, result, now))

    def record_cancelled(
        self,
        *,
        reply_id: str,
        claim_token: str,
        reason_code: str,
        now: datetime,
    ) -> bool:
        return _commit_with_deadlock_retry(
            lambda: self._cancel(reply_id, claim_token, reason_code, now)
        )

    def recover_abandoned_claims(
        self,
        *,
        now: datetime,
        claim_ttl: timedelta = DEFAULT_REPLY_CLAIM_TTL,
        limit: int = 50,
    ) -> int:
        bounded = max(1, min(int(limit), 200))
        return _commit_with_deadlock_retry(lambda: self._recover(now, claim_ttl, bounded))

    def _claim(
        self,
        now: datetime,
        *,
        eligible_phone: str | None = None,
        created_not_before: datetime | None = None,
    ) -> ClaimedReply | None:
        clauses = ["status='pending'"]
        params: list[object] = []
        if eligible_phone:
            clauses.append("normalized_phone=%s")
            params.append(eligible_phone)
        if created_not_before is not None:
            clauses.append("creation>=%s")
            params.append(utc_iso(created_not_before))
        where_sql = " and ".join(clauses)
        rows = frappe.db.sql(
            f"""select name, reply_id, connection_ref, provider_event_id, conversation_id,
                       destination_id, sequence, body, attempt_count, part_kind, document_spec,
                       customer_id, normalized_phone, acceptance_epoch, creation
                from `{_REPLY}`
                where {where_sql}
                order by creation asc, sequence asc
                limit 50
                for update""",
            tuple(params),
            as_dict=True,
        )
        for row in rows:
            if self._blocked(row.connection_ref, row.provider_event_id, int(row.sequence)):
                continue
            token = secrets.token_hex(16)
            attempt_count = int(row.attempt_count) + 1
            frappe.db.sql(
                f"""update `{_REPLY}`
                    set status=%s, attempt_count=%s, claim_token=%s, claimed_on=%s, modified=%s
                    where name=%s and status='pending'""",
                (PROCESSING, attempt_count, token, utc_iso(now), _modified(), row.name),
            )
            owned = frappe.db.sql(
                f"""select status, claim_token from `{_REPLY}` where name=%s""",
                (row.name,),
                as_dict=True,
            )
            if not owned or owned[0].status != PROCESSING or owned[0].claim_token != token:
                continue
            document_spec = None
            if row.document_spec:
                document_spec = document_reply_spec_from_payload(row.document_spec)
            acceptance_epoch = row.acceptance_epoch
            if acceptance_epoch is not None:
                acceptance_epoch = int(acceptance_epoch)
            return ClaimedReply(
                reply_id=row.reply_id,
                claim_token=token,
                connection_ref=row.connection_ref,
                provider_event_id=row.provider_event_id,
                conversation_id=row.conversation_id,
                destination_id=row.destination_id,
                sequence=int(row.sequence),
                body=row.body,
                attempt_count=attempt_count,
                part_kind=row.part_kind or PART_TEXT,
                document_spec=document_spec,
                customer_id=row.customer_id or None,
                normalized_phone=row.normalized_phone or None,
                acceptance_epoch=acceptance_epoch,
                group_document_specs=self._group_document_specs(
                    row.connection_ref, row.provider_event_id
                ),
                created_on=_parse_creation(row.creation),
            )
        return None

    def _group_document_specs(self, connection_ref: str, provider_event_id: str):
        rows = frappe.db.sql(
            f"""select document_spec from `{_REPLY}`
                where connection_ref=%s and provider_event_id=%s
                  and document_spec is not null and document_spec<>''
                order by sequence asc""",
            (connection_ref, provider_event_id),
            as_dict=True,
        )
        specs = []
        for row in rows:
            specs.append(document_reply_spec_from_payload(row.document_spec))
        return tuple(specs)

    def _blocked(self, connection_ref: str, provider_event_id: str, sequence: int) -> bool:
        row = frappe.db.sql(
            f"""select name from `{_REPLY}`
                where connection_ref=%s and provider_event_id=%s and sequence<%s
                  and status<>%s
                limit 1""",
            (connection_ref, provider_event_id, sequence, ACCEPTED),
        )
        return bool(row)

    def _record(self, reply_id: str, claim_token: str, result: TextSendResult, now: datetime) -> bool:
        status = result.disposition.value
        if status not in _TERMINAL or result.reply_id != reply_id:
            return False
        rows = frappe.db.sql(
            f"""select connection_ref, destination_id from `{_REPLY}`
                where reply_id=%s and claim_token=%s and status=%s
                for update""",
            (reply_id, claim_token, PROCESSING),
            as_dict=True,
        )
        if (
            not rows
            or rows[0].connection_ref != result.connection_ref
            or rows[0].destination_id != result.destination_id
        ):
            return False
        provider_message_id = result.provider_message_id if status == ACCEPTED else None
        frappe.db.sql(
            f"""update `{_REPLY}`
                set status=%s, provider_message_id=%s, reason_code=%s, finished_on=%s, modified=%s
                where reply_id=%s and claim_token=%s and status=%s""",
            (
                status,
                provider_message_id,
                result.reason_code,
                utc_iso(now),
                _modified(),
                reply_id,
                claim_token,
                PROCESSING,
            ),
        )
        stored = frappe.db.sql(
            f"""select status from `{_REPLY}`
                where reply_id=%s and claim_token=%s""",
            (reply_id, claim_token),
            as_dict=True,
        )
        return bool(stored) and stored[0].status == status

    def _cancel(self, reply_id: str, claim_token: str, reason_code: str, now: datetime) -> bool:
        rows = frappe.db.sql(
            f"""select name from `{_REPLY}`
                where reply_id=%s and claim_token=%s and status=%s
                for update""",
            (reply_id, claim_token, PROCESSING),
            as_dict=True,
        )
        if not rows:
            return False
        frappe.db.sql(
            f"""update `{_REPLY}`
                set status=%s, reason_code=%s, provider_message_id=null,
                    finished_on=%s, modified=%s
                where reply_id=%s and claim_token=%s and status=%s""",
            (
                CANCELLED,
                reason_code,
                utc_iso(now),
                _modified(),
                reply_id,
                claim_token,
                PROCESSING,
            ),
        )
        stored = frappe.db.sql(
            f"""select status from `{_REPLY}` where reply_id=%s and claim_token=%s""",
            (reply_id, claim_token),
            as_dict=True,
        )
        return bool(stored) and stored[0].status == CANCELLED

    def _recover(self, now: datetime, claim_ttl: timedelta, limit: int) -> int:
        rows = frappe.db.sql(
            f"""select name, claim_token, claimed_on
                from `{_REPLY}`
                where status=%s
                order by claimed_on asc
                limit %s
                for update""",
            (PROCESSING, limit),
            as_dict=True,
        )
        recovered = 0
        finished = utc_iso(now)
        stamp = _modified()
        for row in rows:
            if not claim_is_abandoned(row.claimed_on, now, claim_ttl):
                continue
            if not row.claim_token:
                continue
            frappe.db.sql(
                f"""update `{_REPLY}`
                    set status=%s, reason_code=%s, provider_message_id=null,
                        finished_on=%s, modified=%s
                    where name=%s and claim_token=%s and status=%s""",
                (
                    UNKNOWN,
                    ABANDONED_CLAIM_REASON,
                    finished,
                    stamp,
                    row.name,
                    row.claim_token,
                    PROCESSING,
                ),
            )
            stored = frappe.db.sql(
                f"""select status from `{_REPLY}` where name=%s and claim_token=%s""",
                (row.name, row.claim_token),
                as_dict=True,
            )
            if stored and stored[0].status == UNKNOWN:
                recovered += 1
        return recovered


def _modified() -> str:
    return frappe.utils.now()


def _parse_creation(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        # Frappe often stores naive UTC timestamps.
        if "T" not in text and " " in text:
            text = text.replace(" ", "T", 1)
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = ["FrappeCustomerBotReplyRepository"]
