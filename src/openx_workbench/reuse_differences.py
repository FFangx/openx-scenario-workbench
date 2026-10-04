"""The difference record, and the value comparisons both comparison routes share."""

from __future__ import annotations

from dataclasses import dataclass

from . import reuse_policy as policy


@dataclass(frozen=True, slots=True)
class ReuseDifference:
    category: str
    requested: str
    candidate: str
    action: str
    blocking: bool = False
    cost: float = 1.0
    verified: bool = True


def missing(
    category: str,
    requested: frozenset[str],
    candidate: set[str],
    action: str,
    *,
    blocking: bool = False,
    cost: float = 1.0,
) -> list[ReuseDifference]:
    """One difference per requested value the candidate lacks."""
    return [
        ReuseDifference(category, value, "missing", action, blocking, cost)
        for value in sorted(requested - candidate)
    ]


def parameter_differences(
    requested: tuple[tuple[str, float], ...],
    candidate: dict[str, tuple[float, ...]],
) -> list[ReuseDifference]:
    """Each requested value against the candidate's closest value of that parameter."""
    differences: list[ReuseDifference] = []
    for name, expected in requested:
        values = candidate.get(name, ())
        if not values:
            differences.append(
                ReuseDifference(
                    "parameter",
                    f"{name}={expected:g}",
                    "not extracted",
                    "verify and set parameter in XOSC",
                    cost=policy.COST_PARAMETER,
                )
            )
            continue
        closest = min(values, key=lambda value: abs(value - expected))
        if abs(closest - expected) > policy.PARAMETER_TOLERANCE.get(name, 0.0):
            differences.append(
                ReuseDifference(
                    "parameter",
                    f"{name}={expected:g}",
                    f"{name}={closest:g}",
                    "set parameter in XOSC",
                    cost=policy.COST_PARAMETER,
                )
            )
    return differences


def target_speed_differences(
    requested: tuple[float, ...], candidate: tuple[float, ...]
) -> list[ReuseDifference]:
    if not requested:
        return []
    if len(requested) == len(candidate) and all(
        abs(left - right) <= policy.TARGET_SPEED_TOLERANCE_KPH
        for left, right in zip(requested, candidate)
    ):
        return []
    return [
        ReuseDifference(
            "parameter",
            f"target speeds={requested}",
            str(candidate) if candidate else "not extracted",
            "set target initial speeds",
            cost=policy.COST_PARAMETER,
            verified=bool(candidate),
        )
    ]


def environment_differences(
    requested: tuple[tuple[str, str], ...], candidate: tuple[tuple[str, str], ...]
) -> list[ReuseDifference]:
    environment = dict(candidate)
    differences = []
    for key, expected in requested:
        actual = environment.get(key)
        if actual != expected:
            differences.append(
                ReuseDifference(
                    "environment",
                    f"{key}={expected}",
                    actual or "unknown",
                    "verify or change environment",
                    cost=policy.COST_PARAMETER,
                    verified=actual is not None,
                )
            )
    return differences
