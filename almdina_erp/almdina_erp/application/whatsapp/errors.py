from __future__ import annotations


class WhatsAppError(ValueError):
    """Raised when a WhatsApp use case cannot complete."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WhatsAppTransportError(RuntimeError):
    """Raised by the WhatsApp gateway adapter when OpenWA rejects a call."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str = "transport",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


__all__ = ["WhatsAppError", "WhatsAppTransportError"]
