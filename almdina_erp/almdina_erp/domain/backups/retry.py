"""Framework-free retry policy for external backup jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MAX_BACKUP_ATTEMPTS = 3

# After attempt N fails, wait this many seconds before attempt N+1.
RETRY_DELAY_SECONDS_AFTER_ATTEMPT = {
    1: 60,
    2: 5 * 60,
}

TRANSIENT_ERROR_CODES = frozenset(
    {
        "ssh_connection_failed",
        "ssh_upload_failed",
        "ssh_download_failed",
        "ssh_upload_integrity_failed",
        "ssh_operation_failed",
        "TimeoutError",
        "OSError",
        "ConnectionError",
        "ConnectionResetError",
        "BrokenPipeError",
    }
)

PERMANENT_ERROR_CODES = frozenset(
    {
        "ssh_authentication_failed",
        "ssh_remote_path_invalid",
        "backup_enqueue_failed",
        "backup_retry_exhausted",
        "external_backup_disabled",
        "backup_encryption_public_key_missing",
        "backup_encryption_public_key_invalid",
        "backup_encryption_private_key_rejected",
        "backup_encryption_unavailable",
        "External backup is disabled.",
        "Backup job operation is invalid.",
        "Backup target is invalid.",
        "Backup artifact checksum is invalid.",
        "Backup artifact name is invalid.",
        "Backup artifact is missing.",
    }
)


RetryAction = Literal["retry", "fail"]


@dataclass(frozen=True, slots=True)
class RetryDecision:
    action: RetryAction
    attempt: int
    delay_seconds: int | None
    error_code: str


def normalize_error_code(value: object) -> str:
    return str(value or "backup_operation_failed").strip()[:140] or "backup_operation_failed"


def is_transient_backup_error(error_code: object) -> bool:
    code = normalize_error_code(error_code)
    if code in PERMANENT_ERROR_CODES:
        return False
    if code in TRANSIENT_ERROR_CODES:
        return True
    lowered = code.lower()
    if "authentication" in lowered or "host key" in lowered or "permission" in lowered:
        return False
    if "timeout" in lowered or "temporar" in lowered or "connection" in lowered:
        return True
    return False


def retry_delay_seconds_after_attempt(attempt: int) -> int | None:
    """Return delay before the next attempt after ``attempt`` has failed."""

    try:
        resolved = int(attempt)
    except (TypeError, ValueError):
        return None
    return RETRY_DELAY_SECONDS_AFTER_ATTEMPT.get(resolved)


def decide_external_backup_retry(*, attempt: int, error_code: object) -> RetryDecision:
    """Decide whether the same external operation should be re-queued."""

    code = normalize_error_code(error_code)
    try:
        resolved_attempt = int(attempt)
    except (TypeError, ValueError):
        resolved_attempt = MAX_BACKUP_ATTEMPTS
    if resolved_attempt < 1:
        resolved_attempt = 1

    if not is_transient_backup_error(code) or resolved_attempt >= MAX_BACKUP_ATTEMPTS:
        return RetryDecision(
            action="fail",
            attempt=resolved_attempt,
            delay_seconds=None,
            error_code=code,
        )

    delay = retry_delay_seconds_after_attempt(resolved_attempt)
    if delay is None:
        return RetryDecision(
            action="fail",
            attempt=resolved_attempt,
            delay_seconds=None,
            error_code=code,
        )
    return RetryDecision(
        action="retry",
        attempt=resolved_attempt,
        delay_seconds=delay,
        error_code=code,
    )


__all__ = [
    "MAX_BACKUP_ATTEMPTS",
    "PERMANENT_ERROR_CODES",
    "RETRY_DELAY_SECONDS_AFTER_ATTEMPT",
    "RetryDecision",
    "TRANSIENT_ERROR_CODES",
    "decide_external_backup_retry",
    "is_transient_backup_error",
    "normalize_error_code",
    "retry_delay_seconds_after_attempt",
]
