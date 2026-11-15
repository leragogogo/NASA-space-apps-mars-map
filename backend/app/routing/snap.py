"""Snap clicked points to the nearest valid graph node (SKILL.md section 10, step 3)."""
from __future__ import annotations

from dataclasses import dataclass

from app.graph.loader import RoutingContext


class SnapError(ValueError):
    """A point cannot be used (outside the graph or too far from a valid node). The API answers 422."""


@dataclass(frozen=True)
class SnappedNode:
    node: int
    lon: float
    lat: float
    distance_m: float


def snap(ctx: RoutingContext, lon: float, lat: float, label: str, max_distance_m: float) -> SnappedNode:
    if not bool(ctx.grid.contains(lon, lat)):
        g = ctx.grid
        raise SnapError(f"{label} ({lon:.4f}, {lat:.4f}) is outside the routing area "
                        f"(lon {g.west}..{g.east}, lat {g.south}..{g.north}).")
    dist, idx = ctx.tree.query(ctx.project(lon, lat)[0])
    if dist > max_distance_m:
        raise SnapError(f"{label} ({lon:.4f}, {lat:.4f}) is {dist:.0f} m from the nearest passable-data node "
                        f"(maximum {max_distance_m:.0f} m); it may lie on a nodata area.")
    node = int(ctx.valid_ids[idx])
    return SnappedNode(node, float(ctx.graph.lon[node]), float(ctx.graph.lat[node]), float(dist))
