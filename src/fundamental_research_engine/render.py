from __future__ import annotations

from typing import Any


def _bullet(items: list[str]) -> str:
    if not items:
        return "- None stated"
    return "\n".join(f"- {item}" for item in items)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = ["| " + " | ".join(cell.replace("\n", "<br>") for cell in row) + " |" for row in rows]
    return "\n".join([header_line, separator, *row_lines])


def render_memo(analysis: dict[str, Any]) -> str:
    theme = analysis["theme"]
    bottleneck_rows = [
        [
            item["name"],
            item["rating"],
            f'{item["score"]:.2f}',
            f'{item["positive_score"]:.2f}',
            f'{item["risk_penalty"]:.2f}',
        ]
        for item in analysis["bottleneck_scores"]
    ]
    segment_rows = [
        [
            item["name"],
            item["layer"],
            item["beneficiary_class"],
            item["role"],
            ", ".join(item["representative_companies"]),
        ]
        for item in analysis["segments"]
    ]
    company_rows = [
        [
            item["name"],
            item["product"],
            item["stack_position"],
            item["positioning_label"],
            item["exposure_quality"],
        ]
        for item in analysis["companies"]
    ]
    profit_pool_rows = [
        [
            item["name"],
            item["capture_quality"],
            item["rationale"],
            ", ".join(item["beneficiaries"]),
        ]
        for item in analysis["profit_pools"]
    ]
    scenario_rows = [
        [
            item["name"],
            item["description"],
            "; ".join(item["implications"]),
            "; ".join(item["triggers"]),
        ]
        for item in analysis["scenarios"]
    ]
    evidence_lines = []
    for item in analysis["evidence"]:
        title = item["title"]
        suffix = f' ({item["date"]}, {item["source_type"]}, {item["reliability"]})'
        if item.get("url"):
            title = f'[{title}]({item["url"]})'
        evidence_lines.append(f"- {item['id']}: {title}{suffix}")

    return "\n".join(
        [
            f"# {theme['title']}",
            "",
            f"**As of:** {theme['as_of']}",
            "",
            f"**Type:** `{theme['theme_type']}`",
            "",
            f"**Domain:** `{theme['domain']}`",
            "",
            f"**Core question:** {theme['core_question']}",
            "",
            "## Thesis",
            "",
            theme["thesis"],
            "",
            "## Mechanism",
            "",
            theme["mechanism"] or "No mechanism stated.",
            "",
            "## Maturity Context",
            "",
            f"- Hype stage: `{theme['hype_stage']}`",
            f"- Technology readiness level: `{theme['technology_readiness_level']}`",
            "",
            "### Drivers",
            "",
            _bullet(theme["drivers"]),
            "",
            "## Bottleneck Diagnosis",
            "",
            _table(["Bottleneck", "Rating", "Score", "Positive", "Risk penalty"], bottleneck_rows),
            "",
            "## Industry Chain",
            "",
            _table(["Segment", "Layer", "Class", "Role", "Representative companies"], segment_rows),
            "",
            "## Profit Pools",
            "",
            _table(["Pool", "Capture quality", "Rationale", "Beneficiaries"], profit_pool_rows),
            "",
            "## Company Positioning",
            "",
            _table(["Company", "Product", "Stack position", "Label", "Exposure quality"], company_rows),
            "",
            "## Scenarios",
            "",
            _table(["Scenario", "Description", "Implications", "Triggers"], scenario_rows),
            "",
            "## Counter-Theses",
            "",
            _bullet(analysis["counter_theses"]),
            "",
            "## Tracking Signals",
            "",
            _bullet(analysis["tracking_signals"]),
            "",
            "## Evidence",
            "",
            "\n".join(evidence_lines) if evidence_lines else "- None stated",
            "",
        ]
    )


def _render_string_diff_section(title: str, section: dict[str, Any]) -> list[str]:
    lines = [f"## {title}", ""]
    if not section["added"] and not section["removed"]:
        lines.append("- No changes.")
        lines.append("")
        return lines
    if section["added"]:
        lines.append("**Added:**")
        lines.extend(f"- {item}" for item in section["added"])
    if section["removed"]:
        lines.append("**Removed:**")
        lines.extend(f"- {item}" for item in section["removed"])
    lines.append("")
    return lines


def _render_keyed_diff_section(title: str, key: str, section: dict[str, Any]) -> list[str]:
    lines = [f"## {title}", ""]
    added, removed, changed = section["added"], section["removed"], section["changed"]
    if not added and not removed and not changed:
        lines.append("- No changes.")
        lines.append("")
        return lines
    if added:
        lines.append("**Added:**")
        lines.extend(f"- {item[key]}" for item in added)
    if removed:
        lines.append("**Removed:**")
        lines.extend(f"- {item[key]}" for item in removed)
    if changed:
        lines.append("**Changed:**")
        for item in changed:
            lines.append(f"- {item[key]}:")
            for change in item["changes"]:
                lines.append(f'  - {change["field"]}: `{change["from"]}` -> `{change["to"]}`')
    lines.append("")
    return lines


def render_diff(report: dict[str, Any]) -> str:
    lines = [
        f"# Diff: {report['theme_id']}",
        "",
        f"**From:** {report['from_as_of']}",
        f"**To:** {report['to_as_of']}",
        "",
        "## Theme-Level Changes",
        "",
    ]
    if report["theme_changes"]:
        for change in report["theme_changes"]:
            lines.append(f'- **{change["field"]}**')
            lines.append(f'  - from: {change["from"]}')
            lines.append(f'  - to: {change["to"]}')
    else:
        lines.append("- No changes.")
    lines.append("")

    lines.extend(_render_string_diff_section("Drivers", report["drivers"]))
    lines.extend(_render_keyed_diff_section("Bottleneck Diagnosis", "name", report["bottleneck_scores"]))
    lines.extend(_render_keyed_diff_section("Industry Chain", "name", report["segments"]))
    lines.extend(_render_keyed_diff_section("Profit Pools", "name", report["profit_pools"]))
    lines.extend(_render_keyed_diff_section("Company Positioning", "name", report["companies"]))
    lines.extend(_render_keyed_diff_section("Scenarios", "name", report["scenarios"]))
    lines.extend(_render_keyed_diff_section("Evidence", "id", report["evidence"]))
    lines.extend(_render_string_diff_section("Counter-Theses", report["counter_theses"]))
    lines.extend(_render_string_diff_section("Tracking Signals", report["tracking_signals"]))

    return "\n".join(lines)
