# AGENTS.md — fundamental-research-engine(Codex 读)

Project background: see `PROJECT_CONTEXT.md` (authoritative, detailed) and `README.md`.
This file describes how **you (Codex) collaborate with Claude on the same machine**.

## Dual-AI roundtable protocol
- You and Claude run on the **same VPS, same project directory**, sharing the filesystem.
- The shared blackboard is `DISCUSSION.md` in this directory. Flow:
  1. The user writes a question under "🎯 当前问题" (Current question).
  2. The user asks Claude to append a proposal under "💬 讨论区" (Discussion), signed `@Claude`.
  3. The user switches to you (Codex): read the blackboard, **append** your review / counter-proposal signed `@Codex` with a round number.
  4. Back and forth 1–2 rounds until "✅ 结论" (Conclusion) is agreed.
  5. Split the work per the conclusion, the other side reviews the `git diff`, results go under "🔬 验证记录" (Verification log).
- **Append only — never edit or delete Claude's or the user's entries.** Entry format is in the comments inside `DISCUSSION.md`.

## Machine constraints (important)
- This VPS has only 1 GB RAM; free memory is tight when Claude + Codex run together.
- **Discussion and small edits on the VPS; heavy builds, full test runs, and data backfills go to the user's Windows machine**, with results pasted back into the blackboard. Do not run memory-heavy batch jobs on the VPS.

## Project at a glance
- Python project (`pyproject.toml`), CLI named `fre`, entry via `run.sh` / `run.bat`.
- Source in `src/fundamental_research_engine/`, config in `configs/`, outputs in `reports/` and `runs/`.
- Includes a `fre watch` weekly-report loop, EDGAR ingestion, and a four-gear radar (see PROJECT_CONTEXT.md).
