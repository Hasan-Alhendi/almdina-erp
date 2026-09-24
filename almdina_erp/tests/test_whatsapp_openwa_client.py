from __future__ import annotations

import json
import unittest
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppTransportError
from almdina_erp.almdina_erp.infrastructure.whatsapp.config import OpenWAConfig
from almdina_erp.almdina_erp.infrastructure.whatsapp.openwa_client import OpenWAClient


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class OpenWAClientTests(unittest.TestCase):
    def test_send_document_posts_base64_and_api_key_header(self) -> None:
        captured: dict[str, object] = {}

        def opener(request: Request, timeout: float | None = None) -> FakeResponse:
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse({"messageId": "mid-1", "timestamp": 9})

        client = OpenWAClient(
            OpenWAConfig("http://localhost:2785", "secret"),
            opener=opener,
        )
        receipt = client.send_document(
            "sid",
            "963944123456@c.us",
            filename="file.pdf",
            mimetype="application/pdf",
            data=b"PDF",
        )
        self.assertEqual(receipt.message_id, "mid-1")
        self.assertEqual(
            captured["url"],
            "http://localhost:2785/api/sessions/sid/messages/send-document",
        )
        self.assertEqual(captured["method"], "POST")
        headers = {key.lower(): value for key, value in captured["headers"].items()}  # type: ignore[union-attr]
        self.assertEqual(headers.get("x-api-key") or headers.get("X-API-Key"), "secret")
        body = captured["body"]
        self.assertEqual(body["chatId"], "963944123456@c.us")
        self.assertEqual(body["filename"], "file.pdf")
        self.assertEqual(body["mimetype"], "application/pdf")
        self.assertEqual(body["base64"], "UERG")
        self.assertNotIn("caption", body)

    def test_send_document_includes_caption_on_the_same_message(self) -> None:
        captured: dict[str, object] = {}

        def opener(request: Request, timeout: float | None = None) -> FakeResponse:
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"messageId": "mid-2", "timestamp": 9})

        client = OpenWAClient(
            OpenWAConfig("http://localhost:2785", "secret"),
            opener=opener,
        )
        client.send_document(
            "sid",
            "963944123456@c.us",
            filename="file.pdf",
            mimetype="application/pdf",
            data=b"PDF",
            caption="نرفق القياسات",
        )
        body = captured["body"]
        self.assertEqual(body["caption"], "نرفق القياسات")
        self.assertEqual(body["filename"], "file.pdf")

    def test_http_error_becomes_transport_error(self) -> None:
        def opener(request: Request, timeout: float | None = None) -> FakeResponse:
            raise HTTPError(
                request.full_url,
                409,
                "Conflict",
                hdrs={},
                fp=BytesIO(json.dumps({"message": "not ready"}).encode("utf-8")),
            )

        client = OpenWAClient(
            OpenWAConfig("http://localhost:2785", "secret"),
            opener=opener,
        )
        with self.assertRaises(WhatsAppTransportError) as raised:
            client.send_text("sid", "963944123456@c.us", "hello")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("not ready", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
