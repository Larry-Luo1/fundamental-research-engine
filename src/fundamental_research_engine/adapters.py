from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

Transport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]
CliRunner = Callable[..., subprocess.CompletedProcess[str]]


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
class DeepSeekAdapter:
    model: str
    api_key: str | None = None
    max_tokens: int | None = None
    transport: Transport = field(default=_default_transport)

    def complete(self, prompt: str) -> str:
        api_key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise AdapterError("DEEPSEEK_API_KEY is not set")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            # Every engine prompt expects machine-readable JSON; DeepSeek's
            # JSON Output mode makes retries much less noisy.
            "response_format": {"type": "json_object"},
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        thinking = os.environ.get("DEEPSEEK_THINKING", "disabled").strip().lower()
        if thinking in {"enabled", "disabled"}:
            payload["thinking"] = {"type": thinking}
            if thinking == "enabled":
                payload["reasoning_effort"] = os.environ.get("DEEPSEEK_REASONING_EFFORT", "high")

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        response = self.transport("https://api.deepseek.com/chat/completions", headers, payload)
        try:
            return str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError) as exc:
            raise AdapterError(f"unexpected DeepSeek response shape: {response}") from exc


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


@dataclass
class ClaudeCliAdapter:
    """Run Claude Code locally through its CLI instead of the Anthropic API."""

    model: str | None = None
    command: str | None = None
    timeout_seconds: int = 600
    strip_api_key_env: bool = True
    runner: CliRunner = subprocess.run

    def complete(self, prompt: str) -> str:
        command = self.command or os.environ.get("CLAUDE_CLI_CMD", "claude -p")
        argv = shlex.split(command)
        if self.model:
            argv.extend(["--model", self.model])
        argv.append(prompt)

        env = os.environ.copy()
        if self.strip_api_key_env:
            env.pop("ANTHROPIC_API_KEY", None)

        try:
            completed = self.runner(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
            )
        except FileNotFoundError as exc:
            raise AdapterError("claude CLI was not found; install Claude Code and run `claude login`") from exc
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(f"claude CLI timed out after {self.timeout_seconds} seconds") from exc

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode != 0:
            detail = (stderr or stdout).strip()
            suffix = f": {detail}" if detail else ""
            raise AdapterError(f"claude CLI failed with exit code {completed.returncode}{suffix}")
        if not stdout.strip():
            raise AdapterError("claude CLI returned an empty response")
        return stdout.strip()


@dataclass
class CodexCliAdapter:
    """Run OpenAI Codex locally through its CLI (ChatGPT subscription login, no API key).

    Uses `codex exec` non-interactively: the prompt goes in on stdin (stage
    prompts are large; argv has size limits) and the final assistant message
    comes back through --output-last-message, because codex mixes progress
    logs into stdout. Runs read-only/ephemeral so a completion can never touch
    the filesystem or leave session files behind.
    """

    model: str | None = None
    command: str | None = None
    timeout_seconds: int = 600
    strip_api_key_env: bool = True
    runner: CliRunner = subprocess.run

    def complete(self, prompt: str) -> str:
        command = self.command or os.environ.get("CODEX_CLI_CMD", "codex exec")
        argv = shlex.split(command)
        if self.model:
            argv.extend(["--model", self.model])

        env = os.environ.copy()
        if self.strip_api_key_env:
            # With OPENAI_API_KEY present codex may bill the API instead of
            # the subscription; drop it so the login in ~/.codex is used.
            env.pop("OPENAI_API_KEY", None)

        with tempfile.TemporaryDirectory(prefix="fre-codex-") as tmp_dir:
            out_path = os.path.join(tmp_dir, "last-message.txt")
            argv.extend(
                [
                    "--skip-git-repo-check",
                    "--ephemeral",
                    "--sandbox",
                    "read-only",
                    "--color",
                    "never",
                    "--output-last-message",
                    out_path,
                    "-",
                ]
            )
            try:
                completed = self.runner(
                    argv,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                )
            except FileNotFoundError as exc:
                raise AdapterError("codex CLI was not found; install Codex and run `codex login`") from exc
            except subprocess.TimeoutExpired as exc:
                raise AdapterError(f"codex CLI timed out after {self.timeout_seconds} seconds") from exc

            if completed.returncode != 0:
                detail = ((completed.stderr or "") or (completed.stdout or "")).strip()
                suffix = f": {detail}" if detail else ""
                raise AdapterError(f"codex CLI failed with exit code {completed.returncode}{suffix}")

            output = ""
            if os.path.exists(out_path):
                with open(out_path, encoding="utf-8") as handle:
                    output = handle.read()
        if not output.strip():
            raise AdapterError("codex CLI returned an empty response")
        return output.strip()


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
    if name == "deepseek":
        if not model_name:
            raise ValueError("--model-name is required for the deepseek adapter")
        adapter = DeepSeekAdapter(model=model_name)
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
    if name == "claude-cli":
        return ClaudeCliAdapter(model=model_name)
    if name == "codex":
        return CodexCliAdapter(model=model_name)
    raise ValueError(f"unknown adapter '{name}'")
