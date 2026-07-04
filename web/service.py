"""Orchestration between the web app and the fundamental research engine.

This is a thin layer: it reuses the engine's own drafting/pipeline/diff code
rather than reimplementing any research logic.
"""

from __future__ import annotations

import asyncio
import functools
import time
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
from fundamental_research_engine.primer import build_primer, framing_to_theme_definition
from fundamental_research_engine.prompts import default_methodology_path, render_critique_prompt
from fundamental_research_engine.stages import (
    STAGE_ORDER,
    merge_stage_dicts,
    read_stage_dir_partial,
)
from fundamental_research_engine.validation import validate_theme_dict

from .config import Config, PROJECT_ROOT
from .audit import AuditLogger, sha256_text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _brief_prefix(brief: str, instruction: str | None = None) -> str:
    block = (
        "用户需求：以下是分析师本次要研究的问题。整个主题以及当前阶段都必须严格围绕它展开，"
        "不得跑题；所有面向用户阅读的自然语言内容必须使用简体中文。\n\n"
        f"{brief.strip()}"
    )
    if instruction and instruction.strip():
        block += "\n\n本阶段优化说明：\n" + instruction.strip()
    return block


def model_config_issue(config: Config) -> str | None:
    if config.model == "claude":
        if not config.api_key:
            return "Claude 模型未配置 ANTHROPIC_API_KEY。"
        if config.api_key.startswith("sk-") and not config.api_key.startswith("sk-ant-"):
            return "当前模型设置为 Claude，但配置的 Key 不像 Anthropic Key；如果这是 DeepSeek Key，请设置 FRE_MODEL=deepseek。"
        return None
    if config.model == "deepseek":
        if not config.api_key:
            return "DeepSeek 模型未配置 DEEPSEEK_API_KEY。"
        if config.api_key.startswith("sk-ant-"):
            return "当前模型设置为 DeepSeek，但配置的 Key 像 Anthropic Key；请检查 DEEPSEEK_API_KEY。"
        return None
    if config.model == "openai":
        if not config.api_key:
            return "OpenAI 模型未配置 OPENAI_API_KEY。"
        return None
    return f"未知模型适配器 '{config.model}'。可选值：claude、openai、deepseek。"


class Service:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.project_root = PROJECT_ROOT
        self.sessions_dir = config.data_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLogger(config.data_dir)
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

    def model_config_issue(self) -> str | None:
        return model_config_issue(self.config)

    def audit_events(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.audit.tail(limit)

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
        self.audit.write(
            "analysis_created",
            session_id=sid,
            brief_hash=sha256_text(brief),
            brief_chars=len(brief),
            model=self.config.model,
            model_name=self.config.model_name,
        )
        return sid

    def list_analyses(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for meta_file in self.sessions_dir.glob("*/meta.json"):
            try:
                meta = read_json(meta_file)
            except Exception:  # noqa: BLE001 - skip corrupt session dirs
                continue
            if meta.get("kind") == "primer":
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

    # ---- constraint-radar watch digests (read-only) --------------------
    def _watch_root(self) -> Path:
        return self.project_root / "reports" / "watch"

    def list_watch_digests(self) -> list[dict[str, Any]]:
        """Newest-first index of watch digests written by `fre watch`."""
        root = self._watch_root()
        if not root.exists():
            return []
        items: list[dict[str, Any]] = []
        for date_dir in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
            digest_path = date_dir / "digest.json"
            if not digest_path.is_file():
                continue
            try:
                data = read_json(digest_path)
            except Exception:  # noqa: BLE001 - skip corrupt digests
                continue
            items.append({"as_of": date_dir.name, "watchlist": data.get("watchlist"), "summary": data.get("summary", {})})
        return items

    def get_watch_digest(self, as_of: str) -> dict[str, Any]:
        """Full digest for a date. Raises KeyError if absent or the date is unsafe."""
        if not as_of or "/" in as_of or "\\" in as_of or ".." in as_of:
            raise KeyError(as_of)
        path = self._watch_root() / as_of / "digest.json"
        if not path.is_file():
            raise KeyError(as_of)
        return read_json(path)

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

        issue = self.model_config_issue()
        if issue:
            meta["status"] = "error"
            meta["error"] = issue
            self._write_meta(sid, meta)
            self.audit.write("analysis_config_error", session_id=sid, message=issue, model=self.config.model)
            yield {"event": "error", "message": issue}
            return

        started = time.perf_counter()
        self.audit.write(
            "analysis_started",
            session_id=sid,
            model=self.config.model,
            model_name=self.config.model_name,
            stage_count=len(STAGE_ORDER),
        )
        meta["status"] = "running"
        meta["error"] = None
        self._write_meta(sid, meta)

        existing = read_stage_dir_partial(theme_dir)
        for index, stage in enumerate(STAGE_ORDER, start=1):
            if stage in existing:
                yield {"event": "stage", "stage": stage, "status": "kept", "index": index, "total": len(STAGE_ORDER)}
                continue
            yield {"event": "stage", "stage": stage, "status": "drafting", "index": index, "total": len(STAGE_ORDER)}
            stage_started = time.perf_counter()
            self.audit.write("stage_draft_started", session_id=sid, stage=stage, model=self.config.model)
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
                self.audit.write(
                    "stage_draft_failed",
                    session_id=sid,
                    stage=stage,
                    status=result.status,
                    attempts=result.attempts,
                    duration_ms=round((time.perf_counter() - stage_started) * 1000),
                    error=detail[:1000],
                )
                yield {"event": "error", "stage": stage, "message": meta["error"]}
                return
            self.audit.write(
                "stage_draft_finished",
                session_id=sid,
                stage=stage,
                attempts=result.attempts,
                duration_ms=round((time.perf_counter() - stage_started) * 1000),
            )
            yield {"event": "stage", "stage": stage, "status": "done", "index": index, "total": len(STAGE_ORDER)}

        yield {"event": "validating"}
        ontology = self._ontology()
        merged = merge_stage_dicts(read_stage_dir_partial(theme_dir))
        errors = validate_theme_dict(merged, ontology)
        if errors:
            meta["status"] = "error"
            meta["error"] = "validation failed: " + "; ".join(errors)
            self._write_meta(sid, meta)
            self.audit.write("analysis_validation_failed", session_id=sid, errors=errors[:20])
            yield {"event": "error", "message": meta["error"]}
            return

        yield {"event": "running"}
        pipeline_started = time.perf_counter()
        try:
            run = await loop.run_in_executor(None, functools.partial(self._run_once, sid, theme_dir, meta))
        except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the client
            meta["status"] = "error"
            meta["error"] = f"pipeline failed: {exc}"
            self._write_meta(sid, meta)
            self.audit.write(
                "analysis_pipeline_failed",
                session_id=sid,
                duration_ms=round((time.perf_counter() - pipeline_started) * 1000),
                error=str(exc)[:1000],
            )
            yield {"event": "error", "message": meta["error"]}
            return

        meta["status"] = "done"
        self._write_meta(sid, meta)
        self.audit.write(
            "analysis_finished",
            session_id=sid,
            run_id=run.get("run_id"),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
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

    # ---- primer: fuzzy topic -> orientation + candidate framings -------
    def create_primer(self, topic: str) -> str:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic is empty")
        sid = uuid.uuid4().hex
        self._session_dir(sid).mkdir(parents=True, exist_ok=True)
        self._write_meta(
            sid,
            {
                "id": sid,
                "kind": "primer",
                "topic": topic,
                "created_at": _now(),
                "status": "pending",
                "model": self.config.model,
                "model_name": self.config.model_name,
                "resolved_title": None,
                "error": None,
            },
        )
        self.audit.write(
            "primer_created",
            session_id=sid,
            topic=topic,
            topic_hash=sha256_text(topic),
            model=self.config.model,
            model_name=self.config.model_name,
        )
        return sid

    def _primer_path(self, sid: str) -> Path:
        return self._session_dir(sid) / "primer.json"

    def get_primer(self, sid: str) -> dict[str, Any]:
        meta = self._read_meta(sid)
        path = self._primer_path(sid)
        return {"meta": meta, "primer": read_json(path) if path.exists() else None}

    async def generate_primer(self, sid: str) -> AsyncIterator[dict[str, Any]]:
        lock = self._lock(sid)
        if lock.locked():
            yield {"event": "info", "message": "primer already running"}
            return
        async with lock:
            meta = self._read_meta(sid)
            if meta.get("status") == "done" and self._primer_path(sid).exists():
                yield {"event": "done", "primer": read_json(self._primer_path(sid))}
                return

            yield {"event": "queued"}
            async with self._semaphore():
                loop = asyncio.get_running_loop()
                issue = self.model_config_issue()
                if issue:
                    meta["status"] = "error"
                    meta["error"] = issue
                    self._write_meta(sid, meta)
                    self.audit.write("primer_config_error", session_id=sid, message=issue, model=self.config.model)
                    yield {"event": "error", "message": issue}
                    return
                meta["status"] = "running"
                meta["error"] = None
                self._write_meta(sid, meta)

                yield {"event": "working", "message": "fetching seed sources and organizing the primer"}
                started = time.perf_counter()
                self.audit.write(
                    "primer_started",
                    session_id=sid,
                    topic=meta.get("topic"),
                    model=self.config.model,
                    model_name=self.config.model_name,
                )
                adapter = get_adapter(self.config.model, self.config.model_name, self.config.max_tokens)
                ontology = self._ontology()
                try:
                    result = await loop.run_in_executor(
                        None,
                        functools.partial(
                            build_primer,
                            meta["topic"],
                            adapter,
                            ontology=ontology,
                            prompts_dir=self.project_root / "prompts",
                            max_attempts=self.config.max_attempts,
                        ),
                    )
                except ManualCompletionPending:
                    meta["status"] = "error"
                    meta["error"] = "primer requires a configured model (manual mode is unavailable in the web app)"
                    self._write_meta(sid, meta)
                    self.audit.write(
                        "primer_failed",
                        session_id=sid,
                        duration_ms=round((time.perf_counter() - started) * 1000),
                        error=meta["error"],
                    )
                    yield {"event": "error", "message": meta["error"]}
                    return
                except Exception as exc:  # noqa: BLE001 - surface any failure to the client
                    meta["status"] = "error"
                    meta["error"] = f"primer failed: {exc}"
                    self._write_meta(sid, meta)
                    self.audit.write(
                        "primer_failed",
                        session_id=sid,
                        duration_ms=round((time.perf_counter() - started) * 1000),
                        error=str(exc)[:1000],
                    )
                    yield {"event": "error", "message": meta["error"]}
                    return

                write_json(self._primer_path(sid), result)
                meta["status"] = "done"
                meta["resolved_title"] = result.get("resolved_title")
                self._write_meta(sid, meta)
                primer = result.get("primer", {})
                self.audit.write(
                    "primer_finished",
                    session_id=sid,
                    topic=meta.get("topic"),
                    resolved_title=result.get("resolved_title"),
                    duration_ms=round((time.perf_counter() - started) * 1000),
                    source_count=len(result.get("fetched_sources", [])),
                    framing_count=len(primer.get("candidate_framings", [])) if isinstance(primer, dict) else None,
                    unverified_claim_count=len(result.get("unverified_claims", [])),
                )
                yield {"event": "done", "primer": result}

    def promote_framing(self, sid: str, framing_id: str) -> str:
        """Turn a chosen candidate framing into a fresh, ready-to-draft analysis."""
        data = self.get_primer(sid)
        primer_result = data.get("primer")
        if not primer_result:
            raise ValueError("primer is not ready")
        primer = primer_result.get("primer", {})
        framing = next((f for f in primer.get("candidate_framings", []) if f.get("id") == framing_id), None)
        if framing is None:
            raise ValueError(f"unknown framing '{framing_id}'")

        definition = framing_to_theme_definition(framing, primer)
        brief = f"{framing['title']} — {framing['core_question']}"
        new_sid = self.create_analysis(brief)
        theme_dir = self._session_dir(new_sid) / "theme"
        write_json(theme_dir / "theme_definition.json", definition)
        meta = self._read_meta(new_sid)
        meta["from_primer"] = sid
        meta["from_framing"] = framing_id
        self._write_meta(new_sid, meta)
        self.audit.write("framing_promoted", session_id=sid, analysis_session_id=new_sid, framing_id=framing_id)
        return new_sid

    # ---- critique ------------------------------------------------------
    def critique_stage(self, sid: str, stage: str) -> dict[str, Any]:
        issue = self.model_config_issue()
        if issue:
            self.audit.write("critique_config_error", session_id=sid, stage=stage, message=issue)
            raise RuntimeError(issue)
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
        started = time.perf_counter()
        self.audit.write("critique_started", session_id=sid, stage=stage, model=self.config.model)
        try:
            response = adapter.complete(prompt)
        except ManualCompletionPending:
            self.audit.write("critique_failed", session_id=sid, stage=stage, error="manual completion pending")
            raise RuntimeError("critique requires a configured model (manual mode is unavailable in the web app)")
        except AdapterError as exc:
            self.audit.write("critique_failed", session_id=sid, stage=stage, error=str(exc)[:1000])
            raise RuntimeError(str(exc))

        completion = _complete_json_with_retry(
            adapter, response, prompt, validate_critique_shape, self.config.max_attempts
        )
        if completion.data is None:
            self.audit.write(
                "critique_failed",
                session_id=sid,
                stage=stage,
                attempts=completion.attempts,
                duration_ms=round((time.perf_counter() - started) * 1000),
                error="; ".join(completion.errors)[:1000],
            )
            raise RuntimeError("critique response invalid: " + "; ".join(completion.errors))
        self.audit.write(
            "critique_finished",
            session_id=sid,
            stage=stage,
            attempts=completion.attempts,
            duration_ms=round((time.perf_counter() - started) * 1000),
            concern_count=len(completion.data.get("concerns", [])),
            recommendation=completion.data.get("recommendation"),
        )
        return completion.data

    # ---- iterate: refine one stage, re-run, diff -----------------------
    def refine_and_rerun(self, sid: str, stage: str, instruction: str) -> dict[str, Any]:
        issue = self.model_config_issue()
        if issue:
            self.audit.write("refine_config_error", session_id=sid, stage=stage, message=issue)
            raise RuntimeError(issue)
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
        started = time.perf_counter()
        self.audit.write(
            "refine_started",
            session_id=sid,
            stage=stage,
            instruction_hash=sha256_text(instruction or ""),
            instruction_chars=len(instruction or ""),
        )
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
            self.audit.write(
                "refine_failed",
                session_id=sid,
                stage=stage,
                status=result.status,
                attempts=result.attempts,
                duration_ms=round((time.perf_counter() - started) * 1000),
                error=detail[:1000],
            )
            raise RuntimeError(f"refine failed for {stage}: {detail}")

        ontology = self._ontology()
        merged = merge_stage_dicts(read_stage_dir_partial(theme_dir))
        errors = validate_theme_dict(merged, ontology)
        if errors:
            self.audit.write("refine_validation_failed", session_id=sid, stage=stage, errors=errors[:20])
            raise RuntimeError("validation failed after refine: " + "; ".join(errors))

        run = self._run_once(sid, theme_dir, meta)
        new_analysis = read_json(self._session_dir(sid) / run["dir"] / "analysis.json")
        diff = diff_analysis(old_analysis, new_analysis) if old_analysis is not None else None
        self.audit.write(
            "refine_finished",
            session_id=sid,
            stage=stage,
            run_id=run.get("run_id"),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return {"run": run, "diff": diff}
