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
