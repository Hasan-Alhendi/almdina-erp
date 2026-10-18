"""Customer-bot application errors."""

from __future__ import annotations


class BotReplyPortError(RuntimeError):
    """The injected reply port broke the reply identity contract."""
