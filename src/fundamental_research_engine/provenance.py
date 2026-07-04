from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .claims import verify_quotes
from .evidence import default_fetch, write_evidence_store
from .models import Evidence, Theme


@dataclass(frozen=True)
class ProvenanceBuildResult:
    records: list[dict[str, Any]]
    errors: list[str]


def validate_provenance_spec(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["provenance: expected a JSON object"]
    if "records" not in data:
        return ["provenance.records: missing"]
    if not isinstance(data["records"], list):
        return ["provenance.records: expected list"]

    errors: list[str] = []
    for index, item in enumerate(data["records"]):
        prefix = f"provenance.records[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        unexpected = sorted(
            set(item)
            - {
                "claim_id",
                "quote",
                "confidence",
                "bears_on",
                "source_text",
                "source_text_path",
            }
        )
        for field in unexpected:
            errors.append(f"{prefix}.{field}: unexpected field")
        for field in ("claim_id", "quote", "confidence", "bears_on"):
            if field not in item:
                errors.append(f"{prefix}.{field}: missing")
        if not isinstance(item.get("claim_id"), str) or not item.get("claim_id", "").strip():
            errors.append(f"{prefix}.claim_id: expected non-empty str")
        if not isinstance(item.get("quote"), str) or not item.get("quote", "").strip():
            errors.append(f"{prefix}.quote: expected non-empty str")
        confidence = item.get("confidence")
        if not isinstance(confidence, str):
            errors.append(f"{prefix}.confidence: expected str")
        elif confidence not in {"high", "medium", "low"}:
            errors.append(f"{prefix}.confidence: unknown value '{confidence}'")
        bears_on = item.get("bears_on")
        if not isinstance(bears_on, list):
            errors.append(f"{prefix}.bears_on: expected list")
        else:
            for bears_index, value in enumerate(bears_on):
                if not isinstance(value, str):
                    errors.append(f"{prefix}.bears_on[{bears_index}]: expected str")
        if "source_text" in item and not isinstance(item["source_text"], str):
            errors.append(f"{prefix}.source_text: expected str")
        if "source_text_path" in item and not isinstance(item["source_text_path"], str):
            errors.append(f"{prefix}.source_text_path: expected str")
        if "source_text" in item and "source_text_path" in item:
            errors.append(f"{prefix}: use only one of source_text or source_text_path")
    return errors


def _evidence_claims(theme: Theme) -> dict[str, tuple[Evidence, str]]:
    claims: dict[str, tuple[Evidence, str]] = {}
    for evidence in theme.evidence:
        for index, claim in enumerate(evidence.claims, start=1):
            claims[f"{evidence.id}.C{index}"] = (evidence, claim)
    return claims


def _source_text_for_record(record: dict[str, Any], evidence: Evidence, spec_dir: Path) -> tuple[str | None, str | None]:
    if "source_text" in record:
        return str(record["source_text"]), None
    if "source_text_path" in record:
        path = spec_dir / record["source_text_path"]
        if not path.exists():
            return None, f"source_text_path does not exist: {path}"
        return path.read_text(encoding="utf-8"), None
    if not evidence.url:
        return None, f"{evidence.id}: no url; provide source_text or source_text_path"
    result = default_fetch(evidence.url)
    if not result.ok or not result.text:
        return None, f"{evidence.id}: failed to fetch source: {result.error or result.status}"
    return result.text, None


def build_provenance_records(
    theme: Theme,
    spec: dict[str, Any],
    *,
    spec_dir: Path,
    make_record: Any,
) -> ProvenanceBuildResult:
    errors = validate_provenance_spec(spec)
    if errors:
        return ProvenanceBuildResult(records=[], errors=errors)

    claim_index = _evidence_claims(theme)
    records: list[dict[str, Any]] = []
    for index, item in enumerate(spec["records"]):
        prefix = f"provenance.records[{index}]"
        claim_id = str(item["claim_id"])
        if claim_id not in claim_index:
            errors.append(f"{prefix}.claim_id: unknown applied claim id '{claim_id}'")
            continue
        evidence, claim_text = claim_index[claim_id]
        source_text, error = _source_text_for_record(item, evidence, spec_dir)
        if error:
            errors.append(f"{prefix}: {error}")
            continue
        candidates = [
            {
                "text": claim_text,
                "quote": item["quote"],
                "confidence": item["confidence"],
                "bears_on": [str(value) for value in item["bears_on"]],
            }
        ]
        kept, dropped = verify_quotes(candidates, source_text or "")
        if dropped or len(kept) != 1:
            errors.append(f"{prefix}.quote: quote not found in source text")
            continue
        records.extend(make_record(evidence, kept, source_text))

    return ProvenanceBuildResult(records=records, errors=errors)


def write_provenance_store(
    theme: Theme,
    records: list[dict[str, Any]],
    owners_by_type: dict[str, list[Any]],
    store_root: Path,
) -> dict[str, str]:
    return write_evidence_store(
        theme.id,
        theme.evidence,
        owners_by_type,
        store_root,
        rich_claims=records,
    )
