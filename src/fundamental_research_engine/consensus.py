"""Consensus proxy (gear C) — is a constraint already 'priced in' by the crowd?

The alpha in bottleneck migration lives in the window where a constraint is
tightening but consensus has not yet noticed. We approximate consensus by how
often a constraint is mentioned across a dated corpus of sources over time:

- headroom eroding + mentions still LOW and FLAT  -> pre-consensus window (act)
- mentions RISING                                  -> likely already being priced

Deterministic: given a corpus, the counting is exact. The corpus (dated source
texts) is the input; building it from EDGAR/news/filings is the collection layer.
"""

from __future__ import annotations

import re
from typing import Any


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def constraint_terms(constraint: dict[str, Any]) -> list[str]:
    """Match terms for a constraint: explicit `terms`, else its name."""
    terms = constraint.get("terms")
    if isinstance(terms, list) and terms:
        return [str(term) for term in terms if str(term).strip()]
    name = str(constraint.get("name", "")).strip()
    return [name] if name else []


def consensus_signal(
    terms: list[str],
    documents: list[dict[str, Any]],
    *,
    low: float = 0.2,
    high: float = 0.5,
    eps: float = 0.05,
) -> dict[str, Any]:
    """Fraction of recent vs earlier documents that mention the constraint.

    `documents` are `{date, text}` dicts. Split by date into earlier/recent
    halves; classify the recent mention rate (level) and its move vs the earlier
    baseline (trend). `pre_consensus` is True when the level is low and not rising.
    """
    docs = sorted(
        [d for d in documents if isinstance(d, dict) and d.get("date")],
        key=lambda d: str(d["date"]),
    )
    norm_terms = [t for t in (_norm(term) for term in terms) if t]

    def mentioned(doc: dict[str, Any]) -> bool:
        text = _norm(str(doc.get("text", "")))
        return any(term in text for term in norm_terms)

    n = len(docs)
    if n == 0 or not norm_terms:
        return {"documents": n, "recent_rate": None, "baseline_rate": None, "level": "unknown", "trend": "unknown", "pre_consensus": False}

    flags = [mentioned(doc) for doc in docs]
    split = n // 2
    earlier, recent = flags[:split], flags[split:]
    baseline_rate = round(sum(earlier) / len(earlier), 3) if earlier else None
    recent_rate = round(sum(recent) / len(recent), 3) if recent else 0.0

    level = "low" if recent_rate < low else ("medium" if recent_rate < high else "high")
    if baseline_rate is None:
        trend = "unknown"
    elif recent_rate > baseline_rate + eps:
        trend = "rising"
    elif recent_rate < baseline_rate - eps:
        trend = "falling"
    else:
        trend = "flat"

    pre_consensus = level == "low" and trend in {"flat", "falling", "unknown"}
    return {
        "documents": n,
        "recent_rate": recent_rate,
        "baseline_rate": baseline_rate,
        "level": level,
        "trend": trend,
        "pre_consensus": pre_consensus,
    }
