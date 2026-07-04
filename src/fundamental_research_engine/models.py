from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Evidence:
    id: str
    title: str
    source_type: str
    date: str
    url: str = ""
    reliability: str = "medium"
    claims: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Bottleneck:
    id: str
    name: str
    types: list[str]
    technical_reason: str
    scorecard: dict[str, float]
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Segment:
    id: str
    name: str
    layer: str
    role: str
    beneficiary_class: str
    representative_companies: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProfitPool:
    id: str
    name: str
    rationale: str
    capture_quality: str
    beneficiaries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompanyPosition:
    id: str
    name: str
    product: str
    stack_position: str
    positioning_label: str
    exposure_quality: str
    moat: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    implications: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CausalEdge:
    id: str
    source: str
    target: str
    relationship: str
    transmission: str
    direction: str
    lag: str
    confidence: str
    claim_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Theme:
    id: str
    title: str
    as_of: str
    theme_type: str
    domain: str
    core_question: str
    thesis: str
    mechanism: str
    hype_stage: str
    technology_readiness_level: int
    drivers: list[str]
    bottlenecks: list[Bottleneck]
    segments: list[Segment]
    profit_pools: list[ProfitPool]
    companies: list[CompanyPosition]
    scenarios: list[Scenario]
    evidence: list[Evidence]
    counter_theses: list[str]
    tracking_signals: list[str]
    causal_map: list[CausalEdge] = field(default_factory=list)
    thesis_evidence_ids: list[str] = field(default_factory=list)


def evidence_from_dict(data: dict[str, Any]) -> Evidence:
    return Evidence(
        id=str(data["id"]),
        title=str(data["title"]),
        source_type=str(data["source_type"]),
        date=str(data["date"]),
        url=str(data.get("url", "")),
        reliability=str(data.get("reliability", "medium")),
        claims=[str(item) for item in data.get("claims", [])],
    )


def bottleneck_from_dict(data: dict[str, Any]) -> Bottleneck:
    return Bottleneck(
        id=str(data.get("id", data["name"])),
        name=str(data["name"]),
        types=[str(item) for item in data.get("types", [])],
        technical_reason=str(data["technical_reason"]),
        scorecard={str(key): float(value) for key, value in data.get("scorecard", {}).items()},
        evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
    )


def segment_from_dict(data: dict[str, Any]) -> Segment:
    return Segment(
        id=str(data.get("id", data["name"])),
        name=str(data["name"]),
        layer=str(data["layer"]),
        role=str(data["role"]),
        beneficiary_class=str(data["beneficiary_class"]),
        representative_companies=[str(item) for item in data.get("representative_companies", [])],
    )


def profit_pool_from_dict(data: dict[str, Any]) -> ProfitPool:
    return ProfitPool(
        id=str(data.get("id", data["name"])),
        name=str(data["name"]),
        rationale=str(data["rationale"]),
        capture_quality=str(data["capture_quality"]),
        beneficiaries=[str(item) for item in data.get("beneficiaries", [])],
    )


def company_from_dict(data: dict[str, Any]) -> CompanyPosition:
    return CompanyPosition(
        id=str(data.get("id", data["name"])),
        name=str(data["name"]),
        product=str(data["product"]),
        stack_position=str(data["stack_position"]),
        positioning_label=str(data["positioning_label"]),
        exposure_quality=str(data["exposure_quality"]),
        moat=[str(item) for item in data.get("moat", [])],
        risks=[str(item) for item in data.get("risks", [])],
        evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
    )


def scenario_from_dict(data: dict[str, Any]) -> Scenario:
    return Scenario(
        id=str(data.get("id", data["name"])),
        name=str(data["name"]),
        description=str(data["description"]),
        implications=[str(item) for item in data.get("implications", [])],
        triggers=[str(item) for item in data.get("triggers", [])],
        evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
    )


def causal_edge_from_dict(data: dict[str, Any]) -> CausalEdge:
    return CausalEdge(
        id=str(data.get("id", f"{data['source']}->{data['target']}")),
        source=str(data["source"]),
        target=str(data["target"]),
        relationship=str(data["relationship"]),
        transmission=str(data["transmission"]),
        direction=str(data["direction"]),
        lag=str(data["lag"]),
        confidence=str(data["confidence"]),
        claim_ids=[str(item) for item in data.get("claim_ids", [])],
    )


def theme_from_dict(data: dict[str, Any]) -> Theme:
    drivers = data.get("drivers", data.get("workload_drivers", []))
    return Theme(
        id=str(data["id"]),
        title=str(data["title"]),
        as_of=str(data["as_of"]),
        theme_type=str(data.get("theme_type", "technology_adoption")),
        domain=str(data.get("domain", "ai")),
        core_question=str(data["core_question"]),
        thesis=str(data["thesis"]),
        mechanism=str(data.get("mechanism", "")),
        hype_stage=str(data["hype_stage"]),
        technology_readiness_level=int(data["technology_readiness_level"]),
        drivers=[str(item) for item in drivers],
        bottlenecks=[bottleneck_from_dict(item) for item in data.get("bottlenecks", [])],
        segments=[segment_from_dict(item) for item in data.get("segments", [])],
        profit_pools=[profit_pool_from_dict(item) for item in data.get("profit_pools", [])],
        companies=[company_from_dict(item) for item in data.get("companies", [])],
        scenarios=[scenario_from_dict(item) for item in data.get("scenarios", [])],
        evidence=[evidence_from_dict(item) for item in data.get("evidence", [])],
        counter_theses=[str(item) for item in data.get("counter_theses", [])],
        tracking_signals=[str(item) for item in data.get("tracking_signals", [])],
        causal_map=[causal_edge_from_dict(item) for item in data.get("causal_map", [])],
        thesis_evidence_ids=[str(item) for item in data.get("thesis_evidence_ids", [])],
    )
