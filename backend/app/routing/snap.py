"""Snap clicked points to the nearest valid graph node (SKILL.md section 10, step 3)."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.resources import ProfileId
from app.graph.loader import RoutingContext


class SnapError(ValueError):
    """A point cannot be used (outside the graph or too far from a valid node). The API answers 422."""


@dataclass(frozen=True)
class SnappedNode:
    node: int
    lon: float
    lat: float
    distance_m: float


def snap(ctx: RoutingContext, lon: float, lat: float, label: str, max_distance_m: float,
         profile: ProfileId | str | None = None) -> SnappedNode:
    """Nearest valid node; with `profile`, the nearest node that profile can leave (not on a slope or hazard it
    cannot cross), so a click on a cliff or a dune snaps to usable ground nearby."""
    if not bool(ctx.grid.contains(lon, lat)):
        g = ctx.grid
        raise SnapError(f"{label} ({lon:.4f}, {lat:.4f}) is outside the routing area "
                        f"(lon {g.west}..{g.east}, lat {g.south}..{g.north}).")
    if profile is None:
        tree, ids, what = ctx.tree, ctx.valid_ids, "passable-data node"
    else:
        profile = ProfileId(profile)
        if profile not in ctx.passable:
            raise SnapError(f"No part of the routing area is passable for the {profile.value} profile.")
        (tree, ids), what = ctx.passable[profile], f"node passable for the {profile.value} profile"
    dist, idx = tree.query(ctx.project(lon, lat)[0])
    if dist > max_distance_m:
        raise SnapError(f"{label} ({lon:.4f}, {lat:.4f}) is {dist:.0f} m from the nearest {what} "
                        f"(maximum {max_distance_m:.0f} m); it may lie on a nodata area, a slope too steep "
                        f"for this profile or a blocked hazard zone.")
    node = int(ids[idx])
    return SnappedNode(node, float(ctx.graph.lon[node]), float(ctx.graph.lat[node]), float(dist))
