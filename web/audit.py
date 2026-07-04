"""Append-only operational audit log for the web service."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuditLogger:
    """Tiny JSONL logger for ops/debug events.

    The logger intentionally records metadata rather than prompts, responses, or
    API keys. That keeps the log useful for maintenance without turning it into
    a second sensitive data store.
    """

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "audit" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> None:
        record = {
            "ts": utc_now(),
            "schema_version": 1,
            "event": event,
            **{key: value for key, value in fields.items() if value is not None},
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def tail(self, limit: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        limit = max(1, min(limit, 1000))
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"ts": None, "event": "audit_log_parse_error", "raw": line})
        return events
