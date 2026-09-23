from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import os


ENV_BASE_URL = "OPENWA_BASE_URL"
ENV_API_KEY = "OPENWA_API_KEY"
DEFAULT_BASE_URL = "http://localhost:2785"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def parse_dotenv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return parse_dotenv(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class OpenWAConfig:
    base_url: str
    api_key: str

    @property
    def configured(self) -> bool:
        return bool(self.base_url.strip() and self.api_key.strip())


def load_openwa_config(
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> OpenWAConfig:
    """Load OpenWA settings from process env first, then an optional `.env` file."""

    env = dict(os.environ if environ is None else environ)
    file_values = _read_dotenv(dotenv_path or (_repo_root() / ".env"))
    for key, value in file_values.items():
        env.setdefault(key, value)
    base_url = str(env.get(ENV_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/")
    api_key = str(env.get(ENV_API_KEY) or "").strip()
    return OpenWAConfig(base_url=base_url, api_key=api_key)


__all__ = [
    "DEFAULT_BASE_URL",
    "ENV_API_KEY",
    "ENV_BASE_URL",
    "OpenWAConfig",
    "load_openwa_config",
    "parse_dotenv",
]
