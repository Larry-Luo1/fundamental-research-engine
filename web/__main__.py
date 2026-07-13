"""Entry point: ``python -m web`` starts the server."""

from __future__ import annotations

import uvicorn

from .config import load_config


def main() -> None:
    config = load_config()
    print(f"Fundamental Research Engine web UI on http://{config.host}:{config.port}")
    model_label = f"{config.model}:{config.model_name}" if config.model_name else config.model
    api_status = "not required" if not config.requires_api_key else ("set" if config.has_key else "MISSING")
    print(f"model={model_label}  api_key={api_status}")
    # Single worker keeps the in-process job/session state coherent on a small box.
    uvicorn.run("web.app:app", host=config.host, port=config.port, workers=1, log_level="info")


if __name__ == "__main__":
    main()
