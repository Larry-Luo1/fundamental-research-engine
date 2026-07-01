from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Bottleneck


@dataclass(frozen=True)
class BottleneckScore:
    id: str
    name: str
    score: float
    rating: str
    positive_score: float
    risk_penalty: float
    dimensions: dict[str, float]


def _weighted_average(values: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = 0.0
    weighted_sum = 0.0
    for key, weight in weights.items():
        if key in values:
            weighted_sum += values[key] * float(weight)
            total_weight += float(weight)
    if total_weight == 0:
        return 0.0
    return weighted_sum / total_weight


def _rating(score: float, rules: dict[str, Any]) -> str:
    for item in rules["ratings"]:
        if score >= float(item["min_score"]):
            return str(item["label"])
    return "weak"


def score_bottleneck(bottleneck: Bottleneck, rules: dict[str, Any]) -> BottleneckScore:
    positives = rules["positive_dimensions"]
    negatives = rules["negative_dimensions"]
    positive_score = _weighted_average(bottleneck.scorecard, positives)
    risk_penalty = _weighted_average(bottleneck.scorecard, negatives)

    # Keep the score on the same 0-5 scale while letting major bypass/supply risks matter.
    score = max(0.0, min(5.0, positive_score - risk_penalty * 0.35))
    return BottleneckScore(
        id=bottleneck.id,
        name=bottleneck.name,
        score=round(score, 2),
        rating=_rating(score, rules),
        positive_score=round(positive_score, 2),
        risk_penalty=round(risk_penalty, 2),
        dimensions={key: round(value, 2) for key, value in sorted(bottleneck.scorecard.items())},
    )
