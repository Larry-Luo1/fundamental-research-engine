"""Web layer for the fundamental research engine.

This package is an optional, self-contained web front end. The core engine under
``src/fundamental_research_engine`` stays zero-dependency; only this layer needs
``fastapi``/``uvicorn`` (installed via the ``web`` optional-dependency extra).
"""
