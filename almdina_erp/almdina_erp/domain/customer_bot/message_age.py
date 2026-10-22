"""Age gates for inbound provider timestamps.

``occurred_at`` is the provider message time (OpenWA ``data.timestamp`` in
seconds). It is not the webhook attempt time and not a redelivery clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# OpenWA defaults: retryCount=3, retryDelay base 5s with backoff, timeout up to
# ~25s, plus queue/reconciler slack. Thirty minutes covers that window without
# accepting multi-day history as a fresh conversation start.
DEFAULT_MAX_MESSAGE_AGE = timedelta(minutes=30)
DEFAULT_MAX_FUTURE_SKEW = timedelta(minutes=2)

AGE_OK = "ok"
AGE_STALE = "stale"
AGE_FUTURE = "future"
AGE_INVALID = "invalid"


def classify_message_age(
    occurred_at: datetime | None,
    *,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_MESSAGE_AGE,
    max_future_skew: timedelta = DEFAULT_MAX_FUTURE_SKEW,
) -> str:
    """Classify one provider timestamp against an injected clock."""

    if occurred_at is None:
        return AGE_INVALID
    if occurred_at.utcoffset() is None or now.utcoffset() is None:
        return AGE_INVALID
    if max_age < timedelta(0) or max_future_skew < timedelta(0):
        raise ValueError("age bounds must be non-negative")
    occurred = occurred_at.astimezone(timezone.utc)
    current = now.astimezone(timezone.utc)
    if occurred > current + max_future_skew:
        return AGE_FUTURE
    if occurred < current - max_age:
        return AGE_STALE
    return AGE_OK


__all__ = [
    "AGE_FUTURE",
    "AGE_INVALID",
    "AGE_OK",
    "AGE_STALE",
    "DEFAULT_MAX_FUTURE_SKEW",
    "DEFAULT_MAX_MESSAGE_AGE",
    "classify_message_age",
]
