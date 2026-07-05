"""FastAPI application: shared-password auth + guided analysis over the engine."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import auth
from .config import load_config
from .service import Service

config = load_config()
service = Service(config)

app = FastAPI(title="Fundamental Research Engine", docs_url=None, redoc_url=None)

_STATIC = Path(__file__).resolve().parent / "static"


@app.middleware("http")
async def audit_http_request(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:  # noqa: BLE001 - log then let FastAPI handle it
        service.audit.write(
            "http_request_failed",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - started) * 1000),
            error=str(exc)[:1000],
        )
        raise
    finally:
        service.audit.write(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - started) * 1000),
        )


# ---- auth ------------------------------------------------------------------
def require_auth(request: Request) -> None:
    token = request.cookies.get(auth.COOKIE_NAME, "")
    if not token or not auth.verify_token(token, config.cookie_secret):
        raise HTTPException(status_code=401, detail="not authenticated")


class LoginBody(BaseModel):
    password: str


@app.post("/api/login")
def login(body: LoginBody) -> Response:
    if not auth.check_password(body.password, config.password):
        service.audit.write("login_failed")
        raise HTTPException(status_code=401, detail="wrong password")
    service.audit.write("login_succeeded")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        auth.COOKIE_NAME,
        auth.issue_token(config.cookie_secret),
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )
    return resp


@app.post("/api/logout")
def logout() -> Response:
    service.audit.write("logout")
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME)
    return resp


@app.get("/api/me")
def me(request: Request) -> dict:
    token = request.cookies.get(auth.COOKIE_NAME, "")
    return {"authenticated": bool(token and auth.verify_token(token, config.cookie_secret))}


@app.get("/api/config")
def get_config(_: None = Depends(require_auth)) -> dict:
    issue = service.model_config_issue()
    return {"model": config.model, "model_name": config.model_name, "has_key": config.has_key, "config_error": issue}


@app.get("/api/audit/events")
def get_audit_events(limit: int = 200, _: None = Depends(require_auth)) -> list:
    return service.audit_events(limit)


# ---- analyses --------------------------------------------------------------
class BriefBody(BaseModel):
    brief: str


class CritiqueBody(BaseModel):
    stage: str


class RefineBody(BaseModel):
    stage: str
    instruction: str = ""


class ClientLogBody(BaseModel):
    level: str = "info"
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


def _safe_client_context(context: dict[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in context.items():
        if value is None:
            continue
        safe[str(key)[:80]] = str(value)[:500]
    return safe


@app.post("/api/client-log")
def client_log(body: ClientLogBody, _: None = Depends(require_auth)) -> dict:
    service.audit.write(
        "client_log",
        level=body.level[:40],
        message=body.message[:1000],
        context=_safe_client_context(body.context),
    )
    return {"ok": True}


@app.get("/api/analyses")
def list_analyses(_: None = Depends(require_auth)) -> list:
    return service.list_analyses()


@app.post("/api/analyses")
def create_analysis(body: BriefBody, _: None = Depends(require_auth)) -> dict:
    try:
        sid = service.create_analysis(body.brief)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": sid}


@app.get("/api/analyses/{sid}")
def get_analysis(sid: str, _: None = Depends(require_auth)) -> dict:
    try:
        return service.get_analysis(sid)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="analysis not found")


@app.get("/api/analyses/{sid}/stream")
async def stream_analysis(sid: str, _: None = Depends(require_auth)) -> StreamingResponse:
    try:
        service.get_analysis(sid)  # existence check
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="analysis not found")

    async def event_source():
        try:
            async for event in service.draft_and_run(sid):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 - always close the stream cleanly
            yield f"data: {json.dumps({'event': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/analyses/{sid}/critique")
async def critique(sid: str, body: CritiqueBody, _: None = Depends(require_auth)) -> dict:
    import anyio

    try:
        async with service.guard(sid):
            return await anyio.to_thread.run_sync(service.critique_stage, sid, body.stage)
    except (FileNotFoundError,):
        raise HTTPException(status_code=404, detail="analysis not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/analyses/{sid}/refine")
async def refine(sid: str, body: RefineBody, _: None = Depends(require_auth)) -> dict:
    import anyio

    try:
        async with service.guard(sid):
            return await anyio.to_thread.run_sync(service.refine_and_rerun, sid, body.stage, body.instruction)
    except (FileNotFoundError,):
        raise HTTPException(status_code=404, detail="analysis not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---- primer: fuzzy topic -> orientation + candidate framings ---------------
class TopicBody(BaseModel):
    topic: str


class PromoteBody(BaseModel):
    framing_id: str


@app.post("/api/primers")
def create_primer(body: TopicBody, _: None = Depends(require_auth)) -> dict:
    try:
        sid = service.create_primer(body.topic)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": sid}


@app.get("/api/primers/{sid}")
def get_primer(sid: str, _: None = Depends(require_auth)) -> dict:
    try:
        return service.get_primer(sid)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="primer not found")


@app.get("/api/primers/{sid}/stream")
async def stream_primer(sid: str, _: None = Depends(require_auth)) -> StreamingResponse:
    try:
        service.get_primer(sid)  # existence check
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="primer not found")

    async def event_source():
        try:
            async for event in service.generate_primer(sid):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001 - always close the stream cleanly
            yield f"data: {json.dumps({'event': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/primers/{sid}/promote")
def promote_framing(sid: str, body: PromoteBody, _: None = Depends(require_auth)) -> dict:
    try:
        new_sid = service.promote_framing(sid, body.framing_id)
    except (FileNotFoundError,):
        raise HTTPException(status_code=404, detail="primer not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"analysis_id": new_sid}


# ---- frontend --------------------------------------------------------------
@app.get("/api/watch/digests")
def list_watch_digests(_: None = Depends(require_auth)) -> list:
    return service.list_watch_digests()


@app.get("/api/watch/digests/{as_of}")
def get_watch_digest(as_of: str, _: None = Depends(require_auth)) -> dict:
    try:
        return service.get_watch_digest(as_of)
    except KeyError:
        raise HTTPException(status_code=404, detail="no watch digest for that date")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")
