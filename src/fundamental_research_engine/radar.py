"""Constraint radar — detect where the binding constraint is migrating.

The insight (see docs/monitoring-and-constraint-radar.md): the constraint that
binds next is not found by re-scoring a component and watching its score rise
(that is lagging). It is found by watching the *headroom ratio* of each candidate
constraint erode — capacity_growth / demand_growth. When an upstream driver
accelerates past what a thesis assumed (slope surprise), the adjacent link whose
headroom ratio is smallest and eroding fastest is the next bottleneck.

This module is deterministic (no LLM, no network): growth rates are authored into
a radar spec, and the radar computes ratios, ranks constraints, detects migration
against the prior run's persisted state, and emits typed alerts. The consensus
proxy (gear C) and radar self-calibration (gear D) are layered on separately.

Gears implemented here: A (headroom-ratio erosion), B (slope surprise),
F (persisted radar_state time series).
"""

from __future__ import annotations

from typing import Any

RINGS = {"current_binding", "adjacent_latent", "second_order_external"}

# Defaults; overridable per call.
DEFAULT_MIGRATION_RATIO = 1.15   # a latent link this tight is a migration candidate
DEFAULT_EROSION = 0.05           # ratio drop vs last run that counts as material erosion
DEFAULT_SLOPE_SURPRISE = 0.10    # realized minus assumed driver growth that trips an alert


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def validate_radar_spec(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["radar: expected a JSON object"]
    errors: list[str] = []

    driver = data.get("driver")
    if driver is not None:
        if not isinstance(driver, dict):
            errors.append("radar.driver: expected object")
        else:
            for field in ("realized_growth", "assumed_growth"):
                if field in driver and _num(driver[field]) is None:
                    errors.append(f"radar.driver.{field}: expected number")

    constraints = data.get("constraints")
    if not isinstance(constraints, list) or not constraints:
        errors.append("radar.constraints: expected non-empty list")
        return errors

    seen: set[str] = set()
    for index, item in enumerate(constraints):
        prefix = f"radar.constraints[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix}: expected object")
            continue
        cid = item.get("id")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(f"{prefix}.id: expected non-empty str")
        elif cid in seen:
            errors.append(f"{prefix}.id: duplicate id '{cid}'")
        else:
            seen.add(cid)
        if not isinstance(item.get("name"), str) or not item.get("name", "").strip():
            errors.append(f"{prefix}.name: expected non-empty str")
        ring = item.get("ring")
        if ring not in RINGS:
            errors.append(f"{prefix}.ring: unknown value '{ring}'")
        # Physical constraints need growth numbers; exogenous ones may use a signpost instead.
        if ring != "second_order_external":
            demand = _num(item.get("demand_growth"))
            capacity = _num(item.get("capacity_growth"))
            if demand is None or demand <= 0:
                errors.append(f"{prefix}.demand_growth: expected positive number")
            if capacity is None or capacity < 0:
                errors.append(f"{prefix}.capacity_growth: expected non-negative number")
    return errors


def _derived_candidate_names(theme: Any) -> list[str]:
    names: list[str] = []
    for bottleneck in getattr(theme, "bottlenecks", []):
        names.append(bottleneck.name)
    for edge in getattr(theme, "causal_map", []):
        target = getattr(edge, "target", "")
        if target:
            names.append(target)
    for segment in getattr(theme, "segments", []):
        names.append(segment.name)
    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def _level(ratio: float | None, ratio_delta: float | None, tighter_than_current: bool) -> str:
    if tighter_than_current or (ratio is not None and ratio < 1.0):
        return "action"
    if (ratio is not None and ratio <= DEFAULT_MIGRATION_RATIO) and (
        ratio_delta is not None and ratio_delta <= -DEFAULT_EROSION
    ):
        return "investigate"
    return "watch"


def build_radar(
    theme: Any,
    spec: dict[str, Any],
    prev_entry: dict[str, Any] | None = None,
    *,
    migration_ratio: float = DEFAULT_MIGRATION_RATIO,
    erosion: float = DEFAULT_EROSION,
    slope_surprise_threshold: float = DEFAULT_SLOPE_SURPRISE,
) -> dict[str, Any]:
    """Score candidate constraints, rank by headroom, and flag migration vs the prior run."""
    errors = validate_radar_spec(spec)
    if errors:
        return {"errors": errors}

    prev_ratios = (prev_entry or {}).get("ratios", {}) if isinstance(prev_entry, dict) else {}

    driver = spec.get("driver") or {}
    realized = _num(driver.get("realized_growth"))
    assumed = _num(driver.get("assumed_growth"))
    slope_surprise = round(realized - assumed, 4) if realized is not None and assumed is not None else None

    scored: list[dict[str, Any]] = []
    for item in spec["constraints"]:
        cid = item["id"]
        ring = item["ring"]
        ratio: float | None = None
        demand = _num(item.get("demand_growth"))
        capacity = _num(item.get("capacity_growth"))
        if ring != "second_order_external" and demand and demand > 0 and capacity is not None:
            ratio = round(capacity / demand, 4)
        prev_ratio = prev_ratios.get(cid)
        ratio_delta = round(ratio - prev_ratio, 4) if ratio is not None and isinstance(prev_ratio, (int, float)) else None
        scored.append(
            {
                "id": cid,
                "name": item["name"],
                "ring": ring,
                "demand_growth": demand,
                "capacity_growth": capacity,
                "headroom_ratio": ratio,
                "prev_ratio": prev_ratio if isinstance(prev_ratio, (int, float)) else None,
                "ratio_delta": ratio_delta,
                "binding": ratio is not None and ratio < 1.0,
                "signpost": item.get("signpost"),
            }
        )

    # Tightest current-binding ratio: a latent link tighter than this is migrating in.
    current_ratios = [c["headroom_ratio"] for c in scored if c["ring"] == "current_binding" and c["headroom_ratio"] is not None]
    tightest_current = min(current_ratios) if current_ratios else None

    alerts: list[dict[str, Any]] = []
    if slope_surprise is not None and slope_surprise >= slope_surprise_threshold:
        alerts.append(
            {
                "type": "driver_slope_alert",
                "level": "investigate",
                "driver": driver.get("name", "driver"),
                "message": f"driver realized growth {realized} exceeds thesis-assumed {assumed} (surprise +{slope_surprise})",
                "disconfirming": "realized growth reverts to the assumed slope",
            }
        )

    for constraint in scored:
        ratio = constraint["headroom_ratio"]
        ratio_delta = constraint["ratio_delta"]
        if constraint["ring"] == "adjacent_latent" and ratio is not None:
            tighter_than_current = tightest_current is not None and ratio < tightest_current
            eroding = ratio_delta is not None and ratio_delta <= -erosion
            if ratio <= migration_ratio or tighter_than_current or eroding:
                alerts.append(
                    {
                        "type": "constraint_migration_alert",
                        "level": _level(ratio, ratio_delta, tighter_than_current),
                        "constraint_id": constraint["id"],
                        "message": (
                            f"latent constraint '{constraint['name']}' headroom ratio {ratio}"
                            + (f" (eroded {ratio_delta} vs last run)" if ratio_delta is not None else "")
                            + (" — now tighter than any acknowledged constraint" if tighter_than_current else "")
                        ),
                        "old_ratio": constraint["prev_ratio"],
                        "new_ratio": ratio,
                        "driver_path": f"{driver.get('name', 'driver')} -> {constraint['name']}",
                        "disconfirming": "capacity growth rises to restore headroom ratio above the migration threshold",
                    }
                )

    ranking = sorted(
        [c for c in scored if c["headroom_ratio"] is not None],
        key=lambda c: c["headroom_ratio"],
    )

    uncovered = [n for n in _derived_candidate_names(theme) if n.strip().lower() not in {c["name"].strip().lower() for c in scored}]

    return {
        "theme_id": getattr(theme, "id", spec.get("theme_id")),
        "as_of": spec.get("as_of") or getattr(theme, "as_of", None),
        "driver": {"name": driver.get("name"), "realized_growth": realized, "assumed_growth": assumed, "slope_surprise": slope_surprise},
        "constraints": scored,
        "ranking": [c["id"] for c in ranking],
        "tightest_current_ratio": tightest_current,
        "alerts": alerts,
        "uncovered_candidates": uncovered,
        "state_entry": {
            "as_of": spec.get("as_of") or getattr(theme, "as_of", None),
            "ratios": {c["id"]: c["headroom_ratio"] for c in scored if c["headroom_ratio"] is not None},
            "slope_surprise": slope_surprise,
        },
        "errors": [],
    }
