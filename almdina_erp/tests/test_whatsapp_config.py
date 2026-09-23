from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from almdina_erp.almdina_erp.infrastructure.whatsapp.config import (
    DEFAULT_BASE_URL,
    load_openwa_config,
    parse_dotenv,
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


if __name__ == "__main__":
    unittest.main()
