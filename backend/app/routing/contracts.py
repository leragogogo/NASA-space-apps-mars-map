"""Internal hand-offs between the routing steps: request -> cost matrix -> solver -> assembly.

Point index convention (CostMatrix.nodes): 0 = start, 1..D = destinations in request order,
D+1 = end (only for end_mode "fixed"). Destination indices elsewhere (stop_order, dropped)
are 0-based into the request's destinations. Spec: SKILL.md section 10.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

import numpy as np

from app.core.resources import ProfileId


class EndMode(StrEnum):
    ROUND_TRIP = "round_trip"
    FIXED = "fixed"
    OPEN = "open"


class DropReason(StrEnum):
    UNREACHABLE_FOR_PROFILE = "unreachable_for_profile"
    NOT_SCHEDULED = "not_scheduled_within_time_limit"


@dataclass(frozen=True)
class RouteLimits:
    max_destinations: int = 25
    max_snap_distance_m: float = 1000.0
    default_time_limit_s: float = 5.0
    min_time_limit_s: float = 1.0
    max_time_limit_s: float = 30.0

    def clamp_time_limit(self, value: float | None) -> float:
        v = self.default_time_limit_s if value is None else float(value)
        return min(max(v, self.min_time_limit_s), self.max_time_limit_s)


@dataclass(frozen=True)
class RouteQuery:
    """A request after validation and snapping: everything is a graph node id."""

    profile: ProfileId
    start_node: int
    destination_nodes: tuple[int, ...]
    end_mode: EndMode = EndMode.ROUND_TRIP
    end_node: int | None = None
    time_limit_s: float = 5.0
    season: str | None = None  # for weather warnings only, never for weights

    def __post_init__(self):
        if not self.destination_nodes:
            raise ValueError("at least one destination is required")
        if (self.end_mode == EndMode.FIXED) != (self.end_node is not None):
            raise ValueError("end_node must be given if and only if end_mode is 'fixed'")
        nodes = [self.start_node, *self.destination_nodes] + ([self.end_node] if self.end_node is not None else [])
        if len(set(nodes)) != len(nodes):
            dup = sorted({n for n in nodes if nodes.count(n) > 1})
            raise ValueError(f"snapped points must be distinct; duplicate nodes: {dup}")

    @property
    def point_nodes(self) -> tuple[int, ...]:
        """Graph node of every point, in CostMatrix order."""
        end = (self.end_node,) if self.end_node is not None else ()
        return (self.start_node, *self.destination_nodes, *end)


@dataclass(frozen=True, eq=False)
class CostMatrix:
    """Shortest-path `cost` between all points (not symmetric). inf = unreachable."""

    nodes: tuple[int, ...]
    matrix: np.ndarray  # (N, N) float64, diagonal 0
    legs: Mapping[tuple[int, int], tuple[int, ...]]  # (i, j) -> node path; only finite pairs

    def __post_init__(self):
        n = len(self.nodes)
        if self.matrix.shape != (n, n):
            raise ValueError(f"matrix shape {self.matrix.shape} != ({n}, {n})")
        if np.isnan(self.matrix).any() or (self.matrix < 0).any():
            raise ValueError("matrix must not contain NaN or negative values")
        if (np.diag(self.matrix) != 0).any():
            raise ValueError("matrix diagonal must be 0")

    def reachable(self, i: int, j: int) -> bool:
        return bool(np.isfinite(self.matrix[i, j]))


@dataclass(frozen=True)
class DroppedStop:
    index: int  # into the request's destinations
    reason: DropReason


@dataclass(frozen=True)
class SolverResult:
    order: tuple[int, ...]  # destination indices in visiting order
    dropped: tuple[DroppedStop, ...] = ()


@dataclass(frozen=True)
class Leg:
    from_point: int  # point index (CostMatrix order)
    to_point: int
    nodes: tuple[int, ...]
    cost: float  # unscaled sum of edge costs
    resources: Mapping[str, float] = field(default_factory=dict)  # time_s, o2_g, ...


@dataclass(frozen=True)
class RoutePlan:
    profile: ProfileId
    nodes: tuple[int, ...]  # continuous node path (duplicate join nodes removed)
    stop_order: tuple[int, ...]
    legs: tuple[Leg, ...]
    total_cost: float
    resources: Mapping[str, float]
    dropped: tuple[DroppedStop, ...] = ()
    warnings: tuple[str, ...] = ()
