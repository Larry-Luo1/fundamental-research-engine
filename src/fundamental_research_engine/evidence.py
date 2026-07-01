from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .io import write_json
from .models import Evidence

_RELIABILITY_WEIGHTS = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}


class EvidenceOwner(Protocol):
    id: str
    name: str
    evidence_ids: list[str]


def _reliability_weight(value: str) -> float:
    return _RELIABILITY_WEIGHTS.get(value, 0.5)


def _round_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def evidence_claims(evidence: list[Evidence]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for item in evidence:
        for index, claim in enumerate(item.claims, start=1):
            claims.append(
                {
                    "id": f"{item.id}.C{index}",
                    "evidence_id": item.id,
                    "source_type": item.source_type,
                    "reliability": item.reliability,
                    "date": item.date,
                    "claim": claim,
                }
            )
    return claims


def source_manifest(evidence: list[Evidence]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "date": item.date,
            "url": item.url,
            "reliability": item.reliability,
            "claim_count": len(item.claims),
        }
        for item in evidence
    ]


def coverage_for_owner(owner_type: str, owner: EvidenceOwner, evidence_by_id: dict[str, Evidence]) -> dict[str, Any]:
    known = [evidence_by_id[eid] for eid in owner.evidence_ids if eid in evidence_by_id]
    missing = [eid for eid in owner.evidence_ids if eid not in evidence_by_id]
    claim_count = sum(len(item.claims) for item in known)
    reliability_score = (
        sum(_reliability_weight(item.reliability) for item in known) / len(known)
        if known
        else 0.0
    )

    # This is an audit health score, not a truth score for the investment thesis.
    evidence_depth = min(1.0, len(known) / 2)
    claim_depth = min(1.0, claim_count / 3)
    coverage_score = _round_score(evidence_depth * 0.55 + reliability_score * 0.3 + claim_depth * 0.15)

    if not known:
        status = "missing"
    elif missing:
        status = "partial"
    elif coverage_score >= 0.8:
        status = "strong"
    elif coverage_score >= 0.55:
        status = "adequate"
    else:
        status = "thin"

    return {
        "owner_type": owner_type,
        "owner_id": owner.id,
        "owner_name": owner.name,
        "status": status,
        "coverage_score": coverage_score,
        "evidence_count": len(known),
        "claim_count": claim_count,
        "reliability_score": round(reliability_score, 2),
        "evidence_ids": [item.id for item in known],
        "missing_evidence_ids": missing,
        "evidence_titles": [item.title for item in known],
    }


def build_evidence_audit(
    evidence: list[Evidence],
    owners_by_type: dict[str, list[EvidenceOwner]],
) -> dict[str, Any]:
    evidence_by_id = {item.id: item for item in evidence}
    coverage = [
        coverage_for_owner(owner_type, owner, evidence_by_id)
        for owner_type, owners in owners_by_type.items()
        for owner in owners
    ]
    coverage_scores = [item["coverage_score"] for item in coverage]
    source_types = Counter(item.source_type for item in evidence)
    reliability = Counter(item.reliability for item in evidence)

    return {
        "inventory": {
            "evidence_count": len(evidence),
            "claim_count": sum(len(item.claims) for item in evidence),
            "source_type_counts": dict(sorted(source_types.items())),
            "reliability_counts": dict(sorted(reliability.items())),
        },
        "source_manifest": source_manifest(evidence),
        "claims": evidence_claims(evidence),
        "coverage": coverage,
        "summary": {
            "owners_count": len(coverage),
            "missing_owners_count": sum(1 for item in coverage if item["status"] == "missing"),
            "partial_owners_count": sum(1 for item in coverage if item["status"] == "partial"),
            "average_coverage_score": round(sum(coverage_scores) / len(coverage_scores), 2)
            if coverage_scores
            else 0.0,
        },
        "raw_evidence": [asdict(item) for item in evidence],
    }


def _owner_links(owners_by_type: dict[str, list[EvidenceOwner]]) -> dict[str, list[dict[str, str]]]:
    links: dict[str, list[dict[str, str]]] = {}
    for owner_type, owners in owners_by_type.items():
        for owner in owners:
            for evidence_id in owner.evidence_ids:
                links.setdefault(evidence_id, []).append(
                    {
                        "owner_type": owner_type,
                        "owner_id": owner.id,
                        "owner_name": owner.name,
                    }
                )
    return links


def normalized_evidence_records(
    theme_id: str,
    evidence: list[Evidence],
    owners_by_type: dict[str, list[EvidenceOwner]],
) -> list[dict[str, Any]]:
    links_by_evidence = _owner_links(owners_by_type)
    return [
        {
            "theme_id": theme_id,
            "evidence_id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "date": item.date,
            "url": item.url,
            "reliability": item.reliability,
            "claims": item.claims,
            "claim_ids": [f"{item.id}.C{index}" for index, _ in enumerate(item.claims, start=1)],
            "linked_owners": links_by_evidence.get(item.id, []),
        }
        for item in evidence
    ]


def claim_records(
    theme_id: str,
    evidence: list[Evidence],
    owners_by_type: dict[str, list[EvidenceOwner]],
) -> list[dict[str, Any]]:
    links_by_evidence = _owner_links(owners_by_type)
    records: list[dict[str, Any]] = []
    for item in evidence:
        for index, claim in enumerate(item.claims, start=1):
            records.append(
                {
                    "theme_id": theme_id,
                    "claim_id": f"{item.id}.C{index}",
                    "evidence_id": item.id,
                    "claim": claim,
                    "source_type": item.source_type,
                    "date": item.date,
                    "reliability": item.reliability,
                    "linked_owners": links_by_evidence.get(item.id, []),
                }
            )
    return records


def write_evidence_store(
    theme_id: str,
    evidence: list[Evidence],
    owners_by_type: dict[str, list[EvidenceOwner]],
    store_root: Path,
) -> dict[str, str]:
    raw_dir = store_root / "data" / "raw_sources" / theme_id
    normalized_dir = store_root / "data" / "normalized" / theme_id
    evidence_dir = store_root / "data" / "evidence" / theme_id

    generated_at = datetime.now(timezone.utc).isoformat()
    for item in evidence:
        write_json(
            raw_dir / f"{item.id}.json",
            {
                "theme_id": theme_id,
                "evidence_id": item.id,
                "ingested_at": generated_at,
                "source_snapshot_type": "theme_config_record",
                "source": asdict(item),
            },
        )

    owners_by_evidence = _owner_links(owners_by_type)
    normalized = normalized_evidence_records(theme_id, evidence, owners_by_type)
    claims = claim_records(theme_id, evidence, owners_by_type)
    audit = build_evidence_audit(evidence, owners_by_type)
    manifest = {
        "theme_id": theme_id,
        "generated_at": generated_at,
        "raw_source_dir": str(raw_dir),
        "normalized_evidence_path": str(normalized_dir / "evidence.json"),
        "claims_path": str(evidence_dir / "claims.json"),
        "coverage_path": str(evidence_dir / "coverage.json"),
        "audit_path": str(evidence_dir / "audit.json"),
        "evidence_count": len(evidence),
        "claim_count": len(claims),
        "linked_evidence_count": sum(1 for item in evidence if item.id in owners_by_evidence),
    }

    write_json(normalized_dir / "evidence.json", {"theme_id": theme_id, "records": normalized})
    write_json(evidence_dir / "claims.json", {"theme_id": theme_id, "records": claims})
    write_json(evidence_dir / "coverage.json", {"theme_id": theme_id, "records": audit["coverage"]})
    write_json(evidence_dir / "audit.json", audit)
    write_json(evidence_dir / "manifest.json", manifest)
    return {
        "raw_source_dir": str(raw_dir),
        "normalized_evidence_path": str(normalized_dir / "evidence.json"),
        "claims_path": str(evidence_dir / "claims.json"),
        "coverage_path": str(evidence_dir / "coverage.json"),
        "audit_path": str(evidence_dir / "audit.json"),
        "manifest_path": str(evidence_dir / "manifest.json"),
    }
