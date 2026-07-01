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
    name: str
    types: list[str]
    technical_reason: str
    scorecard: dict[str, float]
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Segment:
    name: str
    layer: str
    role: str
    beneficiary_class: str
    representative_companies: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompanyPosition:
    name: str
    product: str
    stack_position: str
    positioning_label: str
    exposure_quality: str
    moat: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Theme:
    id: str
    title: str
    as_of: str
    core_question: str
    thesis: str
    hype_stage: str
    technology_readiness_level: int
    workload_drivers: list[str]
    bottlenecks: list[Bottleneck]
    segments: list[Segment]
    companies: list[CompanyPosition]
    evidence: list[Evidence]
    counter_theses: list[str]
    tracking_signals: list[str]


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
        name=str(data["name"]),
        types=[str(item) for item in data.get("types", [])],
        technical_reason=str(data["technical_reason"]),
        scorecard={str(key): float(value) for key, value in data.get("scorecard", {}).items()},
        evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
    )


def segment_from_dict(data: dict[str, Any]) -> Segment:
    return Segment(
        name=str(data["name"]),
        layer=str(data["layer"]),
        role=str(data["role"]),
        beneficiary_class=str(data["beneficiary_class"]),
        representative_companies=[str(item) for item in data.get("representative_companies", [])],
    )


def company_from_dict(data: dict[str, Any]) -> CompanyPosition:
    return CompanyPosition(
        name=str(data["name"]),
        product=str(data["product"]),
        stack_position=str(data["stack_position"]),
        positioning_label=str(data["positioning_label"]),
        exposure_quality=str(data["exposure_quality"]),
        moat=[str(item) for item in data.get("moat", [])],
        risks=[str(item) for item in data.get("risks", [])],
        evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
    )


def theme_from_dict(data: dict[str, Any]) -> Theme:
    return Theme(
        id=str(data["id"]),
        title=str(data["title"]),
        as_of=str(data["as_of"]),
        core_question=str(data["core_question"]),
        thesis=str(data["thesis"]),
        hype_stage=str(data["hype_stage"]),
        technology_readiness_level=int(data["technology_readiness_level"]),
        workload_drivers=[str(item) for item in data.get("workload_drivers", [])],
        bottlenecks=[bottleneck_from_dict(item) for item in data.get("bottlenecks", [])],
        segments=[segment_from_dict(item) for item in data.get("segments", [])],
        companies=[company_from_dict(item) for item in data.get("companies", [])],
        evidence=[evidence_from_dict(item) for item in data.get("evidence", [])],
        counter_theses=[str(item) for item in data.get("counter_theses", [])],
        tracking_signals=[str(item) for item in data.get("tracking_signals", [])],
    )
