"""Provider-neutral durable descriptor for a customer-bot document reply.

This is what the outbox stores. It is not a PDF, a public URL, or a session
blob. A later worker re-prepares the file from these fields and must cancel
the intent when the pinned version no longer matches.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .checks import required_token


@dataclass(frozen=True, slots=True)
class DocumentReplySpec:
    service_id: str
    document_type: str
    order_name: str
    consistency_key: str
    filename: str
    mime_type: str
    customer_id: str
    normalized_phone: str
    acceptance_epoch: int
    amount: str | None = None
    currency: str | None = None
    plan_name: str | None = None
    plan_revision: int | None = None
    source_type: str | None = None
    caption: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "service_id", required_token(self.service_id, "service_id"))
        object.__setattr__(self, "document_type", required_token(self.document_type, "document_type"))
        object.__setattr__(self, "order_name", required_token(self.order_name, "order_name"))
        object.__setattr__(
            self, "consistency_key", required_token(self.consistency_key, "consistency_key")
        )
        object.__setattr__(self, "filename", required_token(self.filename, "filename"))
        if self.mime_type != "application/pdf":
            raise ValueError("document mime_type must be application/pdf")
        object.__setattr__(self, "customer_id", required_token(self.customer_id, "customer_id"))
        object.__setattr__(
            self, "normalized_phone", required_token(self.normalized_phone, "normalized_phone")
        )
        if type(self.acceptance_epoch) is not int or self.acceptance_epoch < 0:
            raise ValueError("acceptance_epoch must be a non-negative integer")
        if "/" in self.filename or "\\" in self.filename:
            raise ValueError("document filename must be a safe basename")
        if not isinstance(self.caption, str):
            raise ValueError("document caption must be text")
        object.__setattr__(self, "caption", self.caption.strip())

    def to_payload(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "document_type": self.document_type,
            "order_name": self.order_name,
            "consistency_key": self.consistency_key,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "customer_id": self.customer_id,
            "normalized_phone": self.normalized_phone,
            "acceptance_epoch": self.acceptance_epoch,
            "amount": self.amount,
            "currency": self.currency,
            "plan_name": self.plan_name,
            "plan_revision": self.plan_revision,
            "source_type": self.source_type,
            "caption": self.caption,
        }

    def dumps(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def document_reply_spec_from_payload(raw: Mapping[str, Any] | str | None) -> DocumentReplySpec:
    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = dict(raw or {})
    revision = payload.get("plan_revision")
    return DocumentReplySpec(
        service_id=str(payload.get("service_id") or ""),
        document_type=str(payload.get("document_type") or ""),
        order_name=str(payload.get("order_name") or ""),
        consistency_key=str(payload.get("consistency_key") or ""),
        filename=str(payload.get("filename") or ""),
        mime_type=str(payload.get("mime_type") or "application/pdf"),
        customer_id=str(payload.get("customer_id") or ""),
        normalized_phone=str(payload.get("normalized_phone") or ""),
        acceptance_epoch=int(payload.get("acceptance_epoch") or 0),
        amount=None if payload.get("amount") is None else str(payload.get("amount")),
        currency=None if payload.get("currency") is None else str(payload.get("currency")),
        plan_name=None if payload.get("plan_name") is None else str(payload.get("plan_name")),
        plan_revision=None if revision is None else int(revision),
        source_type=None if payload.get("source_type") is None else str(payload.get("source_type")),
        caption=str(payload.get("caption") or ""),
    )


__all__ = ["DocumentReplySpec", "document_reply_spec_from_payload"]
