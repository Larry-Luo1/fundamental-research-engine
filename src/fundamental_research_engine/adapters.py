from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class ModelAdapter(Protocol):
    def complete(self, prompt: str) -> str: ...


class ManualCompletionPending(Exception):
    """Raised by ManualAdapter: there is no automatic completion, a human must supply one."""

    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        super().__init__("manual completion required; see .prompt for the rendered prompt")


class AdapterError(RuntimeError):
    pass


class ManualAdapter:
    def complete(self, prompt: str) -> str:
        raise ManualCompletionPending(prompt)


def _default_transport(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise AdapterError(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AdapterError(f"failed to reach {url}: {exc.reason}") from exc


@dataclass
class OpenAIAdapter:
    model: str
    api_key: str | None = None
    max_tokens: int | None = None
    transport: Transport = field(default=_default_transport)

    def complete(self, prompt: str) -> str:
        api_key = self.api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise AdapterError("OPENAI_API_KEY is not set")

        payload: dict[str, Any] = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        response = self.transport("https://api.openai.com/v1/chat/completions", headers, payload)
        try:
            return str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as exc:
            raise AdapterError(f"unexpected OpenAI response shape: {response}") from exc


@dataclass
class ClaudeAdapter:
    model: str
    api_key: str | None = None
    # Research stages emit large structured JSON; keep headroom well above the
    # old 4096 default so company_positioning/value_chain_map don't truncate.
    # Non-streaming, so stays under the SDK/HTTP timeout ceiling.
    max_tokens: int = 16000
    transport: Transport = field(default=_default_transport)

    def complete(self, prompt: str) -> str:
        api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise AdapterError("ANTHROPIC_API_KEY is not set")

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        response = self.transport("https://api.anthropic.com/v1/messages", headers, payload)
        try:
            return "".join(block["text"] for block in response["content"] if block.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise AdapterError(f"unexpected Claude response shape: {response}") from exc


def get_adapter(name: str, model_name: str | None = None, max_tokens: int | None = None) -> ModelAdapter:
    if name == "manual":
        return ManualAdapter()
    if name == "openai":
        if not model_name:
            raise ValueError("--model-name is required for the openai adapter")
        adapter = OpenAIAdapter(model=model_name)
        if max_tokens is not None:
            adapter.max_tokens = max_tokens
        return adapter
    if name == "claude":
        if not model_name:
            raise ValueError("--model-name is required for the claude adapter")
        adapter = ClaudeAdapter(model=model_name)
        if max_tokens is not None:
            adapter.max_tokens = max_tokens
        return adapter
    raise ValueError(f"unknown adapter '{name}'")
