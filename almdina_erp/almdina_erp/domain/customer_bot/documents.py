"""Provider-neutral documents prepared for a later customer-bot delivery."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CustomerBotDocument:
    """An in-memory document; conversation state never stores its bytes.

    Provenance fields travel with the object so the outbox can persist a
    descriptor without the PDF. Empty provenance means the caller must not
    create a durable document intent from this value.
    """

    document_type: str
    filename: str
    mime_type: str
    content: bytes
    order_name: str = ""
    consistency_key: str = ""
    service_id: str = ""
    amount: str | None = None
    currency: str | None = None
    plan_name: str | None = None
    plan_revision: int | None = None
    source_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.document_type, str) or not self.document_type.strip():
            raise ValueError("document_type is required")
        if (
            not isinstance(self.filename, str)
            or not self.filename.strip()
            or "/" in self.filename
            or "\\" in self.filename
        ):
            raise ValueError("document filename must be a safe basename")
        if self.mime_type != "application/pdf":
            raise ValueError("customer bot documents must be PDF files")
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("document content is required")

    @property
    def has_durable_provenance(self) -> bool:
        return bool(
            self.order_name.strip()
            and self.consistency_key.strip()
            and self.service_id.strip()
        )


__all__ = ["CustomerBotDocument"]
