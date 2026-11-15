"""POST /api/route logic without HTTP: snap -> validate -> plan -> RouteResponse.

Raises RouteRequestError / SnapError (HTTP 422) and solver.NoFeasibleRoute (HTTP 422).
Spec: SKILL.md section 10, steps 3-6.
"""
from __future__ import annotations

from typing import Callable

from app.core.resources import ProfileId
from app.graph.loader import RoutingContext
from app.routing.contracts import RouteLimits, RoutePlan, RouteQuery
from app.routing.service import plan_route
from app.routing.snap import SnappedNode, snap
from app.schemas.route import (DroppedStopOut, LegOut, LonLat, RouteRequest, RouteResponse, SnappedPoint,
                               SnappedPoints)

WEATHER_UNAVAILABLE = "Weather layer unavailable: dust-storm risk is unknown for this route."


class RouteRequestError(ValueError):
    """The request is well-formed but cannot be routed (e.g. several points snap to one node)."""


def _snapped(s: SnappedNode) -> SnappedPoint:
    return SnappedPoint(lon=s.lon, lat=s.lat, distance_m=round(s.distance_m, 1))


def _label(point: int, n_destinations: int):
    """CostMatrix point index -> API label: "start", destination index or "end"."""
    if point == 0:
        return "start"
    return point - 1 if point <= n_destinations else "end"


def weather_warnings(weather, season: str | None, points: list[tuple[float, float]]) -> list[str]:
    """Weather `message` of the cell of every visited point for the season, verbatim, de-duplicated."""
    if season is None:
        return []
    if weather is None:
        return [WEATHER_UNAVAILABLE]
    key, out = season, []
    for lon, lat in points:
        frame = (weather.sample(lon, lat) or {}).get(key)
        msg = frame["message"] if frame and frame.get("message") else (
            f"No weather data for the area around ({lon:.2f}, {lat:.2f}): dust-storm risk is unknown there.")
        if msg not in out:
            out.append(msg)
    return out


def handle_route_request(ctx: RoutingContext, req: RouteRequest, settings, weather=None) -> RouteResponse:
    limit = settings.max_snap_distance_m
    start = snap(ctx, req.start.lon, req.start.lat, "start", limit)
    dests = [snap(ctx, d.lon, d.lat, f"destination {i}", limit) for i, d in enumerate(req.destinations)]
    end = snap(ctx, req.end.lon, req.end.lat, "end", limit) if req.end else None

    labelled = [("start", start), *((f"destination {i}", s) for i, s in enumerate(dests))]
    if end:
        labelled.append(("end", end))
    seen: dict[int, list[str]] = {}
    for name, s in labelled:
        seen.setdefault(s.node, []).append(name)
    dup = [names for names in seen.values() if len(names) > 1]
    if dup:
        raise RouteRequestError("Points snap to the same graph node and must be distinct: "
                                + "; ".join(" = ".join(n) for n in dup) + ".")

    query = RouteQuery(profile=ProfileId(req.profile), start_node=start.node,
                       destination_nodes=tuple(s.node for s in dests), end_mode=req.end_mode,
                       end_node=end.node if end else None, time_limit_s=req.time_limit_s, season=req.season)
    plan = plan_route(ctx.graph, query, (settings.capacities or {}).get(ProfileId(req.profile).value),
                      settings.reserve_margin)
    visited = [(start.lon, start.lat), *((dests[i].lon, dests[i].lat) for i in plan.stop_order)]
    if end:
        visited.append((end.lon, end.lat))
    warnings = [*plan.warnings, *weather_warnings(weather, req.season, visited)]
    return to_response(ctx, plan, req, start, dests, end, warnings)


def to_response(ctx: RoutingContext, plan: RoutePlan, req: RouteRequest, start: SnappedNode,
                dests: list[SnappedNode], end: SnappedNode | None, warnings: list[str]) -> RouteResponse:
    n = len(dests)
    return RouteResponse(
        profile=plan.profile,
        path={"type": "LineString", "coordinates": ctx.graph.coords(plan.nodes)},
        stop_order=list(plan.stop_order),
        legs=[LegOut(**{"from": _label(leg.from_point, n), "to": _label(leg.to_point, n)},
                     weight=leg.cost, resources=dict(leg.resources)) for leg in plan.legs],
        total_weight=plan.total_cost,
        resources=dict(plan.resources),
        dropped=[DroppedStopOut(index=d.index, point=LonLat(lon=req.destinations[d.index].lon,
                                                            lat=req.destinations[d.index].lat), reason=d.reason)
                 for d in plan.dropped],
        snapped=SnappedPoints(start=_snapped(start), destinations=[_snapped(s) for s in dests],
                              end=_snapped(end) if end else None),
        warnings=warnings,
    )
