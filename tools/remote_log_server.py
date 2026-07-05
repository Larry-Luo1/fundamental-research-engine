"""Read-only HTTP tail server for local Windows runner logs.

The server intentionally exposes only a small allowlist of runtime log files.
It never serves arbitrary paths from the checkout.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SERVICE_NAME = "fre-remote-log-server"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19024
MAX_LINES = 2000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_dotenv_value(root: Path, key: str) -> str | None:
    dotenv = root / ".env"
    if not dotenv.exists():
        return None
    for raw_line in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip().lstrip("\ufeff") != key:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        return value
    return None


def resolve_data_dir(root: Path) -> Path:
    configured = os.environ.get("FRE_WEB_DATA_DIR") or _read_dotenv_value(root, "FRE_WEB_DATA_DIR")
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else (root / path).resolve()
    return root / "web_data"


def log_paths(root: Path) -> dict[str, Path]:
    data_dir = resolve_data_dir(root)
    return {
        "runner": data_dir / "logs" / "runner.log",
        "uvicorn-out": data_dir / "logs" / "uvicorn.out.log",
        "uvicorn-err": data_dir / "logs" / "uvicorn.err.log",
        "remote-log-server-out": data_dir / "logs" / "remote-log-server.out.log",
        "remote-log-server-err": data_dir / "logs" / "remote-log-server.err.log",
        "audit": data_dir / "audit" / "events.jsonl",
    }


def file_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def tail_text(path: Path, line_count: int) -> str:
    line_count = max(1, min(line_count, MAX_LINES))
    if not path.exists():
        return f"[missing] {path}\n"
    if path.is_dir():
        return f"[not a file] {path}\n"

    newline_budget = line_count + 1
    chunks: list[bytes] = []
    chunk_size = 8192
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        seen_newlines = 0
        while position > 0 and seen_newlines <= newline_budget:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            chunks.append(chunk)
            seen_newlines += chunk.count(b"\n")

    data = b"".join(reversed(chunks))
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()[-line_count:]
    return "\n".join(lines) + ("\n" if lines else "")


class LogRequestHandler(BaseHTTPRequestHandler):
    root: Path
    paths: dict[str, Path]

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_text(self, status: HTTPStatus, text: str) -> None:
        self._send_bytes(status, text.encode("utf-8", errors="replace"), "text/plain; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": SERVICE_NAME,
                    "time": utc_now(),
                    "root": str(self.root),
                },
            )
            return

        if parsed.path == "/logs":
            self._send_json(
                HTTPStatus.OK,
                {
                    "service": SERVICE_NAME,
                    "time": utc_now(),
                    "files": {
                        name: {
                            **file_status(path),
                            "tail_url": f"/tail?file={name}&lines=200",
                        }
                        for name, path in self.paths.items()
                    },
                },
            )
            return

        if parsed.path == "/tail":
            name = query.get("file", ["audit"])[0]
            try:
                lines = int(query.get("lines", ["200"])[0])
            except ValueError:
                lines = 200

            if name == "all":
                sections = []
                for item_name, item_path in self.paths.items():
                    sections.append(f"===== {item_name}: {item_path} =====")
                    sections.append(tail_text(item_path, lines))
                self._send_text(HTTPStatus.OK, "\n".join(sections))
                return

            path = self.paths.get(name)
            if path is None:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    {
                        "ok": False,
                        "error": f"unknown log file: {name}",
                        "allowed": sorted(self.paths),
                    },
                )
                return

            self._send_text(HTTPStatus.OK, tail_text(path, lines))
            return

        self._send_json(
            HTTPStatus.NOT_FOUND,
            {
                "ok": False,
                "error": "not found",
                "endpoints": ["/health", "/logs", "/tail?file=audit&lines=200"],
            },
        )

    def log_message(self, format: str, *args: Any) -> None:
        # Keep stdout/stderr quiet; the caller already captures process logs.
        return


def make_handler(root: Path) -> type[LogRequestHandler]:
    paths = log_paths(root)

    class BoundLogRequestHandler(LogRequestHandler):
        pass

    BoundLogRequestHandler.root = root
    BoundLogRequestHandler.paths = paths
    return BoundLogRequestHandler


def serve(root: Path, host: str, port: int) -> None:
    root = root.resolve()
    server = ThreadingHTTPServer((host, port), make_handler(root))
    print(f"{SERVICE_NAME} listening on http://{host}:{port}", flush=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    serve(args.root, args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
