from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from almdina_erp.almdina_erp.domain.customer_bot.operation import callback_url
from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_callback import (
    CUSTOMER_BOT_CALLBACK_PATH,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.config import (
    DEFAULT_BASE_URL,
    ENV_PUBLIC_BASE_URL,
    load_customer_bot_public_base_url,
    load_openwa_config,
    parse_dotenv,
)

_MISSING_DOTENV = Path("/tmp/does-not-exist-almdina.env")
_CALLBACK = (
    "/api/method/almdina_erp.almdina_erp.services.customer_bot_inbound_service"
    ".receive_openwa_customer_bot_event"
)


class OpenWAConfigTests(unittest.TestCase):
    def test_parse_dotenv_ignores_comments_and_exports(self) -> None:
        values = parse_dotenv(
            "\n".join(
                [
                    "# comment",
                    "export OPENWA_BASE_URL=http://localhost:2785",
                    'OPENWA_API_KEY="secret-key"',
                    "",
                    "OTHER=1",
                ]
            )
        )
        self.assertEqual(values["OPENWA_BASE_URL"], "http://localhost:2785")
        self.assertEqual(values["OPENWA_API_KEY"], "secret-key")

    def test_process_environment_wins_over_dotenv(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                "OPENWA_BASE_URL=http://from-file:1\nOPENWA_API_KEY=file-key\n",
                encoding="utf-8",
            )
            config = load_openwa_config(
                {
                    "OPENWA_BASE_URL": "http://from-env:9",
                    "OPENWA_API_KEY": "env-key",
                },
                dotenv_path=path,
            )
        self.assertEqual(config.base_url, "http://from-env:9")
        self.assertEqual(config.api_key, "env-key")

    def test_dotenv_fills_missing_keys_only(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                "OPENWA_BASE_URL=http://from-file:1\nOPENWA_API_KEY=file-key\n",
                encoding="utf-8",
            )
            config = load_openwa_config({}, dotenv_path=path)
        self.assertEqual(config.base_url, "http://from-file:1")
        self.assertEqual(config.api_key, "file-key")
        self.assertTrue(config.configured)

    def test_missing_api_key_is_not_configured(self) -> None:
        config = load_openwa_config({}, dotenv_path=Path("/tmp/does-not-exist.env"))
        self.assertEqual(config.base_url, DEFAULT_BASE_URL)
        self.assertFalse(config.configured)

    def test_public_base_site_value_wins_over_environment(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                f"{ENV_PUBLIC_BASE_URL}=http://from-file:8001\n",
                encoding="utf-8",
            )
            resolved = load_customer_bot_public_base_url(
                {ENV_PUBLIC_BASE_URL: "http://from-env:8001"},
                dotenv_path=path,
                site_value="https://city.example/",
            )
        self.assertEqual(resolved, "https://city.example")

    def test_public_base_environment_wins_over_dotenv_when_site_is_empty(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                f"{ENV_PUBLIC_BASE_URL}=http://from-file:8001\n",
                encoding="utf-8",
            )
            resolved = load_customer_bot_public_base_url(
                {ENV_PUBLIC_BASE_URL: "http://from-env:8001/"},
                dotenv_path=path,
                site_value="  ",
            )
        self.assertEqual(resolved, "http://from-env:8001")

    def test_public_base_dotenv_fills_a_missing_site_and_process_value(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                "\n".join(
                    [
                        f"export {ENV_PUBLIC_BASE_URL}=http://host.docker.internal:8001/",
                        "OPENWA_API_KEY=file-key",
                    ]
                ),
                encoding="utf-8",
            )
            resolved = load_customer_bot_public_base_url({}, dotenv_path=path, site_value="")
            openwa = load_openwa_config({}, dotenv_path=path)
        self.assertEqual(resolved, "http://host.docker.internal:8001")
        self.assertEqual(
            callback_url(resolved, CUSTOMER_BOT_CALLBACK_PATH),
            f"http://host.docker.internal:8001{_CALLBACK}",
        )
        self.assertEqual(CUSTOMER_BOT_CALLBACK_PATH, _CALLBACK)
        self.assertEqual(openwa.api_key, "file-key")
        self.assertEqual(openwa.base_url, DEFAULT_BASE_URL)

    def test_absent_public_base_stays_empty_and_does_not_change_openwa(self) -> None:
        resolved = load_customer_bot_public_base_url(
            {},
            dotenv_path=_MISSING_DOTENV,
            site_value=None,
        )
        openwa = load_openwa_config(
            {"OPENWA_BASE_URL": "http://gateway.example:2785", "OPENWA_API_KEY": "k"},
            dotenv_path=_MISSING_DOTENV,
        )
        self.assertEqual(resolved, "")
        self.assertEqual(openwa.base_url, "http://gateway.example:2785")
        with self.assertRaises(ValueError):
            callback_url(resolved, CUSTOMER_BOT_CALLBACK_PATH)


if __name__ == "__main__":
    unittest.main()
