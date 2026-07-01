from __future__ import annotations

from typing import Any

VALID_SEVERITIES = {"high", "medium", "low"}
VALID_RECOMMENDATIONS = {"accept", "revise"}

_REQUIRED_FIELDS = {"concerns", "overall_assessment", "recommendation"}
_REQUIRED_CONCERN_FIELDS = ["severity", "field", "issue", "suggested_fix"]


def validate_critique_shape(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["critique: expected a JSON object"]

    errors = [f"critique.{field}: missing" for field in sorted(_REQUIRED_FIELDS - set(data))]
    errors += [f"critique.{field}: unexpected field" for field in sorted(set(data) - _REQUIRED_FIELDS)]
    if errors:
        return errors

    concerns = data["concerns"]
    if not isinstance(concerns, list):
        errors.append("critique.concerns: expected list")
    else:
        for index, item in enumerate(concerns):
            prefix = f"critique.concerns[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix}: expected object")
                continue
            for field in _REQUIRED_CONCERN_FIELDS:
                if field not in item:
                    errors.append(f"{prefix}.{field}: missing")
                elif not isinstance(item[field], str):
                    errors.append(f"{prefix}.{field}: expected str, got {type(item[field]).__name__}")
            severity = item.get("severity")
            if isinstance(severity, str) and severity not in VALID_SEVERITIES:
                errors.append(f"{prefix}.severity: unknown value '{severity}'")

    if not isinstance(data.get("overall_assessment"), str):
        errors.append("critique.overall_assessment: expected str")

    recommendation = data.get("recommendation")
    if not isinstance(recommendation, str):
        errors.append("critique.recommendation: expected str")
    elif recommendation not in VALID_RECOMMENDATIONS:
        errors.append(f"critique.recommendation: unknown value '{recommendation}'")

    return errors


def summarize_critique(data: dict[str, Any]) -> str:
    concerns = data.get("concerns", [])
    counts: dict[str, int] = {}
    for item in concerns:
        severity = item.get("severity", "unknown")
        counts[severity] = counts.get(severity, 0) + 1
    counts_text = ", ".join(f"{severity}={count}" for severity, count in sorted(counts.items())) or "none"
    return f"recommendation={data.get('recommendation', 'unknown')} concerns=[{counts_text}]"
