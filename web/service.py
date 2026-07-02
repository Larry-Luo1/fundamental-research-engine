"""Orchestration between the web app and the fundamental research engine.

This is a thin layer: it reuses the engine's own drafting/pipeline/diff code
rather than reimplementing any research logic.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fundamental_research_engine.adapters import AdapterError, ManualCompletionPending, get_adapter
from fundamental_research_engine.cli import _complete_json_with_retry, _fill_stage
from fundamental_research_engine.critique import validate_critique_shape
from fundamental_research_engine.diff import diff_analysis
from fundamental_research_engine.io import read_json, write_json
from fundamental_research_engine.pipeline import default_ontology_path, run_pipeline
from fundamental_research_engine.prompts import default_methodology_path, render_critique_prompt
from fundamental_research_engine.stages import (
    STAGE_ORDER,
    merge_stage_dicts,
    read_stage_dir_partial,
)
from fundamental_research_engine.validation import validate_theme_dict

from .config import Config, PROJECT_ROOT


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brief_prefix(brief: str, instruction: str | None = None) -> str:
    block = (
        "USER BRIEF — the analyst's request. The ENTIRE theme, and this stage in "
        "particular, must be about exactly this topic and stay consistent with it:\n\n"
        f"{brief.strip()}"
    )
    if instruction and instruction.strip():
        block += "\n\nREFINEMENT INSTRUCTION for this stage:\n" + instruction.strip()
    return block


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.project_root = PROJECT_ROOT
        self.sessions_dir = config.data_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._sem: asyncio.Semaphore | None = None
        self._locks: dict[str, asyncio.Lock] = {}

    # ---- infra helpers -------------------------------------------------
    def _semaphore(self) -> asyncio.Semaphore:
        if self._sem is None:
            self._sem = asyncio.Semaphore(max(1, self.config.max_concurrency))
        return self._sem

    def _lock(self, sid: str) -> asyncio.Lock:
        lock = self._locks.get(sid)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[sid] = lock
        return lock

    @asynccontextmanager
    async def guard(self, sid: str):
        """Serialize all mutations of one session and cap global concurrency.

        Every write path (draft / refine / critique) funnels through the same
        per-session lock, so two people (or a double-click) touching the same
        analysis can't clobber its meta.json or stage files; the shared
        semaphore bounds how many run at once across all sessions.
        """
        async with self._lock(sid):
            async with self._semaphore():
                yield

    def _session_dir(self, sid: str) -> Path:
        # sid is a generated uuid hex; still guard against traversal.
        safe = uuid.UUID(sid).hex
        return self.sessions_dir / safe

    def _meta_path(self, sid: str) -> Path:
        return self._session_dir(sid) / "meta.json"

    def _read_meta(self, sid: str) -> dict[str, Any]:
        return read_json(self._meta_path(sid))

    def _write_meta(self, sid: str, meta: dict[str, Any]) -> None:
        write_json(self._meta_path(sid), meta)

    def _ontology(self) -> dict[str, Any]:
        return read_json(default_ontology_path(self.project_root))

    # ---- session lifecycle --------------------------------------------
    def create_analysis(self, brief: str) -> str:
        brief = brief.strip()
        if not brief:
            raise ValueError("brief is empty")
        sid = uuid.uuid4().hex
        (self._session_dir(sid) / "theme").mkdir(parents=True, exist_ok=True)
        (self._session_dir(sid) / "runs").mkdir(parents=True, exist_ok=True)
        self._write_meta(
            sid,
            {
                "id": sid,
                "brief": brief,
                "created_at": _now(),
                "status": "pending",
                "model": self.config.model,
                "model_name": self.config.model_name,
                "runs": [],
                "error": None,
            },
        )
        return sid

    def list_analyses(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for meta_file in self.sessions_dir.glob("*/meta.json"):
            try:
                meta = read_json(meta_file)
            except Exception:  # noqa: BLE001 - skip corrupt session dirs
                continue
            items.append(
                {
                    "id": meta.get("id"),
                    "brief": meta.get("brief"),
                    "created_at": meta.get("created_at"),
                    "status": meta.get("status"),
                    "runs": len(meta.get("runs", [])),
                }
            )
        items.sort(key=lambda m: m.get("created_at") or "", reverse=True)
        return items

    def get_analysis(self, sid: str) -> dict[str, Any]:
        meta = self._read_meta(sid)
        theme_dir = self._session_dir(sid) / "theme"
        stages = read_stage_dir_partial(theme_dir)
        result: dict[str, Any] = {"meta": meta, "stages": stages, "analysis": None, "memo": None}
        runs = meta.get("runs", [])
        if runs:
            run_dir = self._session_dir(sid) / runs[-1]["dir"]
            analysis_path = run_dir / "analysis.json"
            memo_path = run_dir / "memo.md"
            if analysis_path.exists():
                result["analysis"] = read_json(analysis_path)
            if memo_path.exists():
                result["memo"] = memo_path.read_text(encoding="utf-8")
        return result

    # ---- guided drafting + run (streamed) ------------------------------
    async def draft_and_run(self, sid: str) -> AsyncIterator[dict[str, Any]]:
        lock = self._lock(sid)
        if lock.locked():
            yield {"event": "info", "message": "analysis already running"}
            return

        async with lock:
            meta = self._read_meta(sid)
            if meta.get("status") == "done":
                yield {"event": "done", "message": "already complete", "run": meta["runs"][-1]}
                return

            # Tell the client we're waiting for a free slot (no-op if one is free).
            yield {"event": "queued"}
            async with self._semaphore():
                async for event in self._run_pipeline_job(sid, meta):
                    yield event

    async def _run_pipeline_job(self, sid: str, meta: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        theme_dir = self._session_dir(sid) / "theme"
        prefix = _brief_prefix(meta["brief"])

        meta["status"] = "running"
        meta["error"] = None
        self._write_meta(sid, meta)

        existing = read_stage_dir_partial(theme_dir)
        for index, stage in enumerate(STAGE_ORDER, start=1):
            if stage in existing:
                yield {"event": "stage", "stage": stage, "status": "kept", "index": index, "total": len(STAGE_ORDER)}
                continue
            yield {"event": "stage", "stage": stage, "status": "drafting", "index": index, "total": len(STAGE_ORDER)}
            result = await loop.run_in_executor(
                None,
                functools.partial(
                    _fill_stage,
                    theme_dir,
                    stage,
                    self.project_root,
                    self.config.model,
                    self.config.model_name,
                    self.config.max_attempts,
                    self.config.max_tokens,
                    prefix,
                ),
            )
            if result.status != "written":
                detail = "; ".join(result.errors) if result.errors else result.status
                meta["status"] = "error"
                meta["error"] = f"{stage}: {detail}"
                self._write_meta(sid, meta)
                yield {"event": "error", "stage": stage, "message": meta["error"]}
                return
            yield {"event": "stage", "stage": stage, "status": "done", "index": index, "total": len(STAGE_ORDER)}

        yield {"event": "validating"}
        ontology = self._ontology()
        merged = merge_stage_dicts(read_stage_dir_partial(theme_dir))
        errors = validate_theme_dict(merged, ontology)
        if errors:
            meta["status"] = "error"
            meta["error"] = "validation failed: " + "; ".join(errors)
            self._write_meta(sid, meta)
            yield {"event": "error", "message": meta["error"]}
            return

        yield {"event": "running"}
        try:
            run = await loop.run_in_executor(None, functools.partial(self._run_once, sid, theme_dir, meta))
        except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the client
            meta["status"] = "error"
            meta["error"] = f"pipeline failed: {exc}"
            self._write_meta(sid, meta)
            yield {"event": "error", "message": meta["error"]}
            return

        meta["status"] = "done"
        self._write_meta(sid, meta)
        yield {"event": "done", "run": run}

    def _run_once(self, sid: str, theme_dir: Path, meta: dict[str, Any]) -> dict[str, Any]:
        run_index = len(meta.get("runs", [])) + 1
        rel_dir = f"runs/run-{run_index}"
        out_dir = self._session_dir(sid) / rel_dir
        run_pipeline(theme_dir, self.project_root, out_dir)
        analysis = read_json(out_dir / "analysis.json")
        run_record = {
            "run_id": f"run-{run_index}",
            "dir": rel_dir,
            "as_of": analysis.get("theme", {}).get("as_of"),
            "created_at": _now(),
        }
        meta.setdefault("runs", []).append(run_record)
        self._write_meta(sid, meta)
        return run_record

    # ---- critique ------------------------------------------------------
    def critique_stage(self, sid: str, stage: str) -> dict[str, Any]:
        if stage not in STAGE_ORDER:
            raise ValueError(f"unknown stage '{stage}'")
        theme_dir = self._session_dir(sid) / "theme"
        existing = read_stage_dir_partial(theme_dir)
        if stage not in existing:
            raise ValueError(f"stage '{stage}' has not been drafted yet")

        ontology = self._ontology()
        theme_type = existing.get("theme_definition", {}).get("theme_type")
        methodology = None
        if theme_type:
            methodology_path = default_methodology_path(self.project_root, theme_type)
            if methodology_path.exists():
                methodology = read_json(methodology_path)

        prompt = render_critique_prompt(
            stage, existing[stage], self.project_root / "prompts", existing, ontology, methodology
        )
        adapter = get_adapter(self.config.model, self.config.model_name, self.config.max_tokens)
        try:
            response = adapter.complete(prompt)
        except ManualCompletionPending:
            raise RuntimeError("critique requires a configured model (manual mode is unavailable in the web app)")
        except AdapterError as exc:
            raise RuntimeError(str(exc))

        completion = _complete_json_with_retry(
            adapter, response, prompt, validate_critique_shape, self.config.max_attempts
        )
        if completion.data is None:
            raise RuntimeError("critique response invalid: " + "; ".join(completion.errors))
        return completion.data

    # ---- iterate: refine one stage, re-run, diff -----------------------
    def refine_and_rerun(self, sid: str, stage: str, instruction: str) -> dict[str, Any]:
        if stage not in STAGE_ORDER:
            raise ValueError(f"unknown stage '{stage}'")
        meta = self._read_meta(sid)
        theme_dir = self._session_dir(sid) / "theme"
        existing = read_stage_dir_partial(theme_dir)
        if stage not in existing:
            raise ValueError(f"stage '{stage}' has not been drafted yet")

        old_analysis = None
        runs = meta.get("runs", [])
        if runs:
            old_path = self._session_dir(sid) / runs[-1]["dir"] / "analysis.json"
            if old_path.exists():
                old_analysis = read_json(old_path)

        prefix = _brief_prefix(meta["brief"], instruction)
        result = _fill_stage(
            theme_dir,
            stage,
            self.project_root,
            self.config.model,
            self.config.model_name,
            self.config.max_attempts,
            self.config.max_tokens,
            prefix,
        )
        if result.status != "written":
            detail = "; ".join(result.errors) if result.errors else result.status
            raise RuntimeError(f"refine failed for {stage}: {detail}")

        ontology = self._ontology()
        merged = merge_stage_dicts(read_stage_dir_partial(theme_dir))
        errors = validate_theme_dict(merged, ontology)
        if errors:
            raise RuntimeError("validation failed after refine: " + "; ".join(errors))

        run = self._run_once(sid, theme_dir, meta)
        new_analysis = read_json(self._session_dir(sid) / run["dir"] / "analysis.json")
        diff = diff_analysis(old_analysis, new_analysis) if old_analysis is not None else None
        return {"run": run, "diff": diff}
