"""Provider-neutral documents prepared for a later customer-bot delivery."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CustomerBotDocument:
    """An in-memory document; it is never serialized into conversation state."""

    document_type: str
    filename: str
    mime_type: str
    content: bytes

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


__all__ = ["CustomerBotDocument"]
