"""A document reply request for a gateway adapter.

The request carries PDF bytes prepared after preflight. It does not carry a
public URL, a session secret, or conversation state.
"""

from __future__ import annotations

from dataclasses import dataclass

from .checks import required_token


@dataclass(frozen=True, slots=True)
class DocumentReplyRequest:
    reply_id: str
    connection_ref: str
    destination_id: str
    filename: str
    mime_type: str
    content: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "reply_id", required_token(self.reply_id, "reply_id"))
        object.__setattr__(self, "connection_ref", required_token(self.connection_ref, "connection_ref"))
        object.__setattr__(
            self,
            "destination_id",
            required_token(self.destination_id, "destination_id"),
        )
        object.__setattr__(self, "filename", required_token(self.filename, "filename"))
        if "/" in self.filename or "\\" in self.filename:
            raise ValueError("document filename must be a safe basename")
        if self.mime_type != "application/pdf":
            raise ValueError("document mime_type must be application/pdf")
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("document content is required")


__all__ = ["DocumentReplyRequest"]
