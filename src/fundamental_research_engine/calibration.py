"""Calibration loop: turn a theme's forward-looking statements into dated,
checkable predictions, resolve them over time, and score how well-calibrated the
research process has been.

This is the "keep quality high over time" half of the quality gate. A track
record is a JSON file per theme; ``fre calibrate`` registers/resolves
predictions and ``fre qc`` folds the resulting calibration into the scorecard.

Like the rest of the quality layer, calibration is a *process-health* signal: it
measures whether we make and honestly resolve predictions, not whether any
single thesis is right.
"""

from __future__ import annotations

import hashlib
from typing import Any

# Where a prediction came from. Tracking signals and scenario triggers are the
# natural "if this happens, the thesis is (in)validated" statements.
PREDICTION_KINDS = ("tracking_signal", "counter_thesis", "scenario_trigger")


def prediction_key(kind: str, statement: str) -> str:
    digest = hashlib.sha256(f"{kind}::{statement.strip()}".encode("utf-8")).hexdigest()
    return digest[:12]


def extract_predictions(theme: Any) -> list[dict[str, Any]]:
    """Derive candidate predictions from a theme's forward-looking statements."""
    records: list[dict[str, Any]] = []

    def add(kind: str, statement: str) -> None:
        statement = statement.strip()
        if not statement:
            return
        records.append(
            {
                "key": prediction_key(kind, statement),
                "kind": kind,
                "statement": statement,
                "registered_as_of": theme.as_of,
                "probability": None,
                "resolved": False,
                "outcome": None,
                "resolved_as_of": None,
            }
        )

    for signal in theme.tracking_signals:
        add("tracking_signal", signal)
    for counter in theme.counter_theses:
        add("counter_thesis", counter)
    for scenario in theme.scenarios:
        for trigger in scenario.triggers:
            add("scenario_trigger", trigger)
    return records


def register_predictions(record: dict[str, Any], theme: Any) -> dict[str, Any]:
    """Merge newly-extracted predictions into a track record, preserving resolved ones."""
    record = {"theme_id": theme.id, "predictions": list(record.get("predictions", []))}
    existing = {item["key"] for item in record["predictions"]}
    for prediction in extract_predictions(theme):
        if prediction["key"] not in existing:
            record["predictions"].append(prediction)
            existing.add(prediction["key"])
    return record


def resolve_prediction(
    record: dict[str, Any],
    key: str,
    outcome: bool,
    resolved_as_of: str,
) -> bool:
    """Mark a prediction resolved. Returns True if the key was found."""
    for prediction in record.get("predictions", []):
        if prediction["key"] == key:
            prediction["resolved"] = True
            prediction["outcome"] = bool(outcome)
            prediction["resolved_as_of"] = resolved_as_of
            return True
    return False


def build_calibration(record: dict[str, Any]) -> dict[str, Any]:
    """Compute calibration stats over a track record (deterministic, no LLM)."""
    predictions = record.get("predictions", [])
    resolved = [item for item in predictions if item.get("resolved")]
    resolved_true = sum(1 for item in resolved if item.get("outcome") is True)
    resolved_false = sum(1 for item in resolved if item.get("outcome") is False)

    scored = [
        item
        for item in resolved
        if isinstance(item.get("probability"), (int, float))
        and not isinstance(item.get("probability"), bool)
        and item.get("outcome") is not None
    ]
    brier: float | None = None
    if scored:
        total = 0.0
        for item in scored:
            probability = float(item["probability"])
            actual = 1.0 if item["outcome"] else 0.0
            total += (probability - actual) ** 2
        brier = round(total / len(scored), 4)

    as_of_runs = len({item.get("registered_as_of") for item in predictions if item.get("registered_as_of")})

    return {
        "predictions": len(predictions),
        "resolved": len(resolved),
        "open": len(predictions) - len(resolved),
        "resolved_true": resolved_true,
        "resolved_false": resolved_false,
        "resolution_rate": round(len(resolved) / len(predictions), 2) if predictions else 0.0,
        "brier": brier,
        "track_record_runs": as_of_runs,
    }
