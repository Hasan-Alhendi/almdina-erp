"""HTTP transport for customer-bot OpenWA sends.

Separate from ``OpenWAClient`` so the bot path can inject a fake opener in
tests without changing the factory WhatsApp client. Errors never include the
request body, API key, or base64 payload.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.infrastructure.whatsapp.config import OpenWAConfig

from .customer_bot_openwa_send import CustomerBotOpenWASendTransport, OpenWASendHttpRequest

_Opener = Callable[..., Any]


class UrlOpenCustomerBotOpenWATransport:
    """Posts JSON to the local OpenWA gateway with ``X-API-Key`` auth."""

    def __init__(
        self,
        config: OpenWAConfig,
        *,
        opener: _Opener | None = None,
        timeout: float = 45,
    ) -> None:
        if not config.configured:
            raise WhatsAppTransportError(
                "WhatsApp gateway is not configured.",
                code="not_configured",
            )
        self._base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key
        self._opener = opener or urlopen
        self._timeout = timeout

    def post_json(self, request: OpenWASendHttpRequest) -> Mapping[str, Any]:
        if request.method != "POST":
            raise WhatsAppTransportError("unsupported method", code="send_unknown")
        encoded = json.dumps(request.body).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-Key": self._api_key,
        }
        http_request = Request(
            f"{self._base_url}{request.path}",
            data=encoded,
            headers=headers,
            method="POST",
        )
        try:
            with self._opener(http_request, timeout=self._timeout) as response:
                raw = response.read()
                if not raw:
                    return {}
                parsed = json.loads(raw.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise WhatsAppTransportError(
                        "gateway response shape invalid",
                        code="invalid_response",
                    )
                return parsed
        except HTTPError as error:
            status = int(error.code)
            try:
                error.close()
            except Exception:
                pass
            # Do not surface response bodies: they may echo media or keys.
            raise WhatsAppTransportError(
                f"OpenWA rejected send ({status}).",
                status_code=status,
            ) from None
        except TimeoutError as error:
            raise WhatsAppTransportError(
                "OpenWA send timed out.",
                code="timeout",
            ) from error
        except URLError as error:
            reason = getattr(error, "reason", None)
            timed_out = isinstance(reason, TimeoutError) or "timed out" in str(reason or "").lower()
            raise WhatsAppTransportError(
                "OpenWA send timed out." if timed_out else "OpenWA gateway unreachable.",
                code="timeout" if timed_out else "unreachable",
            ) from None
        except json.JSONDecodeError as error:
            raise WhatsAppTransportError(
                "OpenWA response was not JSON.",
                code="invalid_response",
            ) from error


def assert_is_bot_send_transport(value: object) -> CustomerBotOpenWASendTransport:
    if not hasattr(value, "post_json"):
        raise TypeError("transport must provide post_json")
    return value  # type: ignore[return-value]


__all__ = [
    "UrlOpenCustomerBotOpenWATransport",
    "assert_is_bot_send_transport",
]
