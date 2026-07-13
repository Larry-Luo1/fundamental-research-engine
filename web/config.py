"""Runtime configuration, read from the environment (see .env.example)."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

# Repo root = parent of the web/ package. knowledge/, prompts/, src/ live here,
# so a git clone gives the engine everything it needs with no data bundling.
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    password: str
    api_key: str
    model: str
    model_name: str
    max_tokens: int
    max_attempts: int
    max_concurrency: int
    data_dir: Path
    cookie_secret: bytes
    host: str
    port: int

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)

    @property
    def requires_api_key(self) -> bool:
        return self.model in {"claude", "openai", "deepseek"}


def load_config() -> Config:
    password = os.environ.get("FRE_WEB_PASSWORD", "").strip()
    if not password:
        raise RuntimeError(
            "FRE_WEB_PASSWORD is not set. Copy .env.example to .env, set a shared "
            "password (and ANTHROPIC_API_KEY), then start the server."
        )

    model = os.environ.get("FRE_MODEL", "claude-cli").strip()
    default_model_name = {
        "claude": "claude-opus-4-8",
        "claude-cli": "",
        "codex": "",
        "deepseek": "deepseek-v4-pro",
        "openai": "gpt-4.1",
    }.get(model, "")
    model_name = os.environ.get("FRE_MODEL_NAME", default_model_name).strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if model == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if model == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

    data_dir = Path(os.environ.get("FRE_WEB_DATA_DIR", str(PROJECT_ROOT / "web_data"))).resolve()

    # Cookie signing secret: explicit if provided, else derived from the password
    # so restarts keep sessions valid without extra config.
    secret_raw = os.environ.get("FRE_WEB_SECRET", "").strip() or f"fre::{password}"
    cookie_secret = hashlib.sha256(secret_raw.encode("utf-8")).digest()

    return Config(
        password=password,
        api_key=api_key,
        model=model,
        model_name=model_name,
        max_tokens=int(os.environ.get("FRE_MAX_TOKENS", "16000")),
        max_attempts=int(os.environ.get("FRE_MAX_ATTEMPTS", "2")),
        max_concurrency=int(os.environ.get("FRE_MAX_CONCURRENCY", "4")),
        data_dir=data_dir,
        cookie_secret=cookie_secret,
        host=os.environ.get("FRE_HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", os.environ.get("FRE_PORT", "8000"))),
    )
