"""Shared helpers for coaxing valid JSON out of a model and retrying on failure.

Extracted from cli.py so both the CLI (fill/draft/critique) and other callers
(e.g. the quality module) can reuse the same JSON-extraction and
retry-on-validation-error behavior without importing CLI internals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterError


def parse_model_json(response: str) -> dict[str, Any]:
    text = response.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    candidates: list[str] = []
    if "```" in text:
        parts = text.split("```")
        candidates.extend(part.strip().removeprefix("json").strip() for part in parts[1::2])
    candidates.append(text)

    for candidate in candidates:
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
            raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
    raise ValueError("model response did not contain a valid JSON object")


def retry_prompt(prompt: str, errors: list[str]) -> str:
    details = "\n".join(f"- {error}" for error in errors)
    return (
        f"{prompt}\n\n"
        "The previous response was rejected for these issues:\n"
        f"{details}\n\n"
        "Return only one corrected JSON object for the requested stage."
    )


@dataclass
class CompletionAttempt:
    data: dict[str, Any] | None
    response: str
    errors: list[str]
    attempts: int
    adapter_error: bool = False


def complete_json_with_retry(
    adapter: Any,
    initial_response: str,
    prompt: str,
    validate: Any,
    max_attempts: int,
) -> CompletionAttempt:
    max_attempts = max(1, max_attempts)
    attempt = 1
    last_response = initial_response
    while True:
        try:
            data = parse_model_json(last_response)
            errors = validate(data)
        except ValueError as exc:
            data = None
            errors = [str(exc)]

        if data is not None and not errors:
            return CompletionAttempt(data=data, response=last_response, errors=[], attempts=attempt)

        if attempt >= max_attempts:
            return CompletionAttempt(data=None, response=last_response, errors=errors, attempts=attempt)
        attempt += 1
        try:
            last_response = adapter.complete(retry_prompt(prompt, errors))
        except AdapterError as exc:
            return CompletionAttempt(
                data=None, response=last_response, errors=[str(exc)], attempts=attempt, adapter_error=True
            )
