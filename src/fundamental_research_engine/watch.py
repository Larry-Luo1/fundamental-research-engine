"""Weekly monitoring loop — tie the radar gears into a gated digest.

`fre watch <watchlist.json>` runs the constraint radar across a set of themes and
produces one digest that surfaces ONLY themes with material change. The red-line
from docs/monitoring-and-constraint-radar.md: no daily noise — alert on divergence
(migration / slope surprise / pre-consensus window / headroom erosion), each with a
disconfirming condition, and feed migration calls back into calibration.

This module orchestrates; the signal-producing logic lives in radar.py /
consensus.py / diff.py and is reused verbatim. Deterministic given inputs.
"""

from __future__ import annotations

from typing import Any

from .radar import DEFAULT_EROSION

LEVEL_RANK = {"action": 3, "investigate": 2, "watch": 1, "none": 0}

_DIFF_SECTIONS = [
    "theme_changes", "drivers", "bottleneck_scores", "causal_map", "segments",
    "profit_pools", "companies", "scenarios", "evidence", "counter_theses", "tracking_signals",
]


def summarize_analysis_diff(diff_report: dict[str, Any]) -> dict[str, Any]:
    """Count how many analysis sections changed between two pipeline runs."""
    changed = 0
    for key in _DIFF_SECTIONS:
        section = diff_report.get(key)
        if isinstance(section, list):
            if section:
                changed += 1
        elif isinstance(section, dict):
            if any(section.get(k) for k in ("added", "removed", "changed")):
                changed += 1
    return {
        "changed": changed > 0,
        "sections_changed": changed,
        "from_as_of": diff_report.get("from_as_of"),
        "to_as_of": diff_report.get("to_as_of"),
    }


def validate_watchlist(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["watchlist: expected a JSON object"]
    errors: list[str] = []
    themes = data.get("themes")
    if not isinstance(themes, list) or not themes:
        errors.append("watchlist.themes: expected non-empty list")
        return errors
    for index, entry in enumerate(themes):
        prefix = f"watchlist.themes[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: expected object")
            continue
        for field in ("theme", "radar_spec"):
            if not isinstance(entry.get(field), str) or not entry.get(field, "").strip():
                errors.append(f"{prefix}.{field}: expected non-empty str (path)")
        if "corpus" in entry and not isinstance(entry["corpus"], str):
            errors.append(f"{prefix}.corpus: expected str (path)")
    return errors


def gate_radar(radar: dict[str, Any], *, erosion: float = DEFAULT_EROSION) -> dict[str, Any]:
    """Decide whether a theme's radar warrants surfacing, and why."""
    alerts = radar.get("alerts", [])
    migrations = [a for a in alerts if a.get("type") == "constraint_migration_alert"]
    reasons: list[str] = []

    if any(a.get("type") == "driver_slope_alert" for a in alerts):
        reasons.append("driver slope surprise")
    if any(a.get("level") == "action" for a in migrations):
        reasons.append("action-level constraint migration")
    elif any(a.get("level") == "investigate" for a in migrations):
        reasons.append("investigate-level constraint migration")
    if any(a.get("pre_consensus") for a in migrations):
        reasons.append("pre-consensus alpha window")
    eroded = [
        c for c in radar.get("constraints", [])
        if isinstance(c.get("ratio_delta"), (int, float)) and c["ratio_delta"] <= -erosion
    ]
    if eroded:
        reasons.append(f"headroom eroded on {len(eroded)} constraint(s)")

    levels = [a.get("level") for a in alerts]
    top_level = next((lvl for lvl in ("action", "investigate", "watch") if lvl in levels), "none")
    return {"material": bool(reasons), "reasons": reasons, "top_level": top_level}


def theme_result(radar: dict[str, Any], *, analysis_diff: dict[str, Any] | None = None, erosion: float = DEFAULT_EROSION) -> dict[str, Any]:
    """Condense a radar report into one digest row for a theme."""
    gate = gate_radar(radar, erosion=erosion)
    migrations = [a for a in radar.get("alerts", []) if a.get("type") == "constraint_migration_alert"]
    by_id = {c["id"]: c for c in radar.get("constraints", [])}
    tightest = radar["ranking"][0] if radar.get("ranking") else None
    tightest_ratio = by_id[tightest]["headroom_ratio"] if tightest in by_id else None
    return {
        "theme_id": radar.get("theme_id"),
        "as_of": radar.get("as_of"),
        "tightest": tightest,
        "tightest_ratio": tightest_ratio,
        "material": gate["material"],
        "top_level": gate["top_level"],
        "reasons": gate["reasons"],
        "migration_alerts": [
            {"constraint_id": a["constraint_id"], "level": a["level"], "pre_consensus": a.get("pre_consensus", False), "message": a["message"]}
            for a in migrations
        ],
        "pre_consensus": [a["constraint_id"] for a in migrations if a.get("pre_consensus")],
        "slope_surprise": radar.get("driver", {}).get("slope_surprise"),
        "calibration": radar.get("calibration"),
        "analysis_diff": analysis_diff,
    }


def build_digest(results: list[dict[str, Any]], *, as_of: str, watchlist_name: str | None = None) -> dict[str, Any]:
    """Rank flagged themes; list quiet ones by id only (no noise)."""
    ok = [r for r in results if not r.get("error")]
    flagged = [r for r in ok if r["material"]]
    quiet = [r["theme_id"] for r in ok if not r["material"]]
    errored = [{"theme_id": r["theme_id"], "error": r["error"]} for r in results if r.get("error")]

    flagged.sort(key=lambda r: (-LEVEL_RANK.get(r["top_level"], 0), r["tightest_ratio"] if r["tightest_ratio"] is not None else 9e9))
    return {
        "as_of": as_of,
        "watchlist": watchlist_name,
        "themes_scanned": len(results),
        "summary": {
            "flagged": len(flagged),
            "quiet": len(quiet),
            "action": sum(1 for r in flagged if r["top_level"] == "action"),
            "pre_consensus": sum(1 for r in flagged if r["pre_consensus"]),
            "errored": len(errored),
        },
        "flagged": flagged,
        "quiet": quiet,
        "errored": errored,
    }


def render_digest_md(digest: dict[str, Any]) -> str:
    lines: list[str] = []
    name = digest.get("watchlist") or "watchlist"
    lines.append(f"# Constraint radar digest — {name} — {digest['as_of']}")
    s = digest["summary"]
    lines.append("")
    lines.append(
        f"Scanned {digest['themes_scanned']} theme(s): **{s['flagged']} flagged** "
        f"({s['action']} action, {s['pre_consensus']} pre-consensus), {s['quiet']} quiet, {s['errored']} errored."
    )

    if digest["flagged"]:
        lines.append("")
        lines.append("## Flagged")
        for row in digest["flagged"]:
            ratio = row["tightest_ratio"]
            lines.append("")
            lines.append(f"### {row['theme_id']} — {row['top_level'].upper()}  (tightest: {row['tightest']} @ {ratio})")
            lines.append(f"- Why: {'; '.join(row['reasons'])}")
            if row.get("slope_surprise"):
                lines.append(f"- Driver slope surprise: +{row['slope_surprise']}")
            for alert in row["migration_alerts"]:
                # alert["message"] already carries the [pre-consensus] tag when applicable.
                lines.append(f"- [{alert['level']}] {alert['message']}")
            if row.get("analysis_diff") is not None:
                ad = row["analysis_diff"]
                lines.append(f"- Analysis run diff: {'changed' if ad.get('changed') else 'no change'} ({ad.get('sections_changed', 0)} section(s))")
            if row.get("calibration"):
                cal = row["calibration"]
                lines.append(f"- Radar calibration: {cal['resolved']}/{cal['predictions']} resolved, Brier={cal.get('brier')}")

    if digest["quiet"]:
        lines.append("")
        lines.append(f"## Quiet (no material change)\n{', '.join(digest['quiet'])}")
    if digest["errored"]:
        lines.append("")
        lines.append("## Errored")
        for row in digest["errored"]:
            lines.append(f"- {row['theme_id']}: {row['error']}")
    return "\n".join(lines) + "\n"
