"""POST /api/route logic without HTTP: snap -> validate -> plan -> RouteResponse.

Raises RouteRequestError / SnapError (HTTP 422) and solver.NoFeasibleRoute (HTTP 422).
profile "auto" routes with every profile and keeps the one app.routing.modes.choose picks (NoProfileCanRoute, a NoFeasibleRoute, when none can).
Spec: SKILL.md section 10, steps 3-6.
"""
from __future__ import annotations

import math
from typing import Callable

from app.core.resources import PROFILES, ProfileId
from app.graph.loader import RoutingContext
from app.routing.contracts import RoutePlan, RouteQuery
from app.routing.modes import AUTO, ProfileOutcome, choose
from app.routing.profiles.params import CarParams
from app.routing.profiles.personalize import (graph_matches_models, path_resources_for_mass, reference_models,
                                             supports_body_mass)
from app.routing.service import plan_route
from app.routing.snap import SnappedNode, SnapError, snap
from app.routing.solver import NoFeasibleRoute
from app.schemas.route import (DroppedStopOut, LegOut, LonLat, ModeSelection, ProfileOption, RouteRequest,
                               RouteResponse, SnappedPoint, SnappedPoints)

WEATHER_UNAVAILABLE = "Weather layer unavailable: dust-storm risk is unknown for this route."
MASS_UNAVAILABLE = ("Oxygen, CO2 and water use are estimated for the reference astronaut mass: the routing graph was "
                    "built with other profile parameters than the current ones (rebuild it with `python -m app.graph`).")
USER_CHOICE = "Chosen by the user."


class RouteRequestError(ValueError):
    """The request is well-formed but cannot be routed (e.g. several points snap to one node)."""


ROUTE_ERRORS = (SnapError, RouteRequestError, NoFeasibleRoute)


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


def mass_resources(ctx: RoutingContext, profile: ProfileId, body_mass_kg: float | None, settings):
    """(path_resources callable | None, mass used | None, warning | None) for the requesting user's body mass."""
    if body_mass_kg is None or not supports_body_mass(profile):
        return None, None, None
    models = reference_models(settings)
    if not graph_matches_models(ctx.formula_version, models):
        return None, None, MASS_UNAVAILABLE
    model = models[profile]
    return (lambda _profile, nodes: path_resources_for_mass(ctx.graph, model, nodes, body_mass_kg),
            float(body_mass_kg), None)


def crew_size(settings, profile: ProfileId) -> int:
    """People whose oxygen a profile's o2_g covers: one walker, or the rover's crew.

    The car's o2_g in the stored graph uses the crew_n it was built with; after changing crew_n,
    rebuild the graph (python -m app.graph) so the two agree.
    """
    if profile != ProfileId.CAR:
        return 1
    return max(1, CarParams(**(settings.profiles or {}).get("car", {})).crew_n)


def _outcome(response: RouteResponse, requested: int, crew: int) -> ProfileOutcome:
    return ProfileOutcome(response.profile, reached=len(response.stop_order), requested=requested,
                          o2_g=response.resources.get("o2_g", 0.0) / crew, time_s=response.resources.get("time_s", 0.0))


def _option(o: ProfileOutcome) -> ProfileOption:
    finite = lambda v: v if math.isfinite(v) else None  # noqa: E731
    return ProfileOption(profile=o.profile, feasible=o.feasible, reached=o.reached, o2_g=finite(o.o2_g),
                         time_s=finite(o.time_s), reason=o.error)


def handle_route_request(ctx: RoutingContext, req: RouteRequest, settings, weather=None,
                         body_mass_kg: float | None = None) -> RouteResponse:
    limits = settings.route_limits
    if len(req.destinations) > limits.max_destinations:
        raise RouteRequestError(f"At most {limits.max_destinations} destinations are allowed per request "
                                f"(got {len(req.destinations)}).")
    n, time_limit = len(req.destinations), limits.clamp_time_limit(req.time_limit_s)
    if req.profile != AUTO:
        profile = ProfileId(req.profile)
        response = route_for_profile(ctx, req, profile, settings, weather, body_mass_kg, time_limit)
        mode = ModeSelection(requested=req.profile, chosen=profile, reason=USER_CHOICE,
                             options=[_option(_outcome(response, n, crew_size(settings, profile)))])
        return response.model_copy(update={"mode": mode})
    # Each profile gets an equal share of the solver budget (never below min_time_limit_s), so auto takes about as long
    # as one profile, or up to twice the minimum when the request asks for the minimum.
    share = max(limits.min_time_limit_s, time_limit / len(PROFILES))
    responses: dict[ProfileId, RouteResponse] = {}
    outcomes: list[ProfileOutcome] = []
    for profile in PROFILES:
        try:
            responses[profile] = route_for_profile(ctx, req, profile, settings, weather, body_mass_kg, share)
        except ROUTE_ERRORS as ex:
            outcomes.append(ProfileOutcome(profile, requested=n, error=str(ex)))
        else:
            outcomes.append(_outcome(responses[profile], n, crew_size(settings, profile)))
    best, reason = choose(outcomes)  # NoProfileCanRoute (HTTP 422) when no profile can route
    mode = ModeSelection(requested=AUTO, chosen=best.profile, reason=reason, options=[_option(o) for o in outcomes])
    return responses[ProfileId(best.profile)].model_copy(update={"mode": mode})


def route_for_profile(ctx: RoutingContext, req: RouteRequest, profile: ProfileId, settings, weather,
                      body_mass_kg: float | None, time_limit_s: float) -> RouteResponse:
    """One profile: snap every point to a node that profile can use, reject duplicates, plan, convert."""
    limit = settings.max_snap_distance_m
    start = snap(ctx, req.start.lon, req.start.lat, "start", limit, profile)
    dests = [snap(ctx, d.lon, d.lat, f"destination {i}", limit, profile) for i, d in enumerate(req.destinations)]
    end = snap(ctx, req.end.lon, req.end.lat, "end", limit, profile) if req.end else None

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

    query = RouteQuery(profile=profile, start_node=start.node, destination_nodes=tuple(s.node for s in dests),
                       end_mode=req.end_mode, end_node=end.node if end else None, time_limit_s=time_limit_s,
                       season=req.season)
    resources_of, mass_used, mass_warning = mass_resources(ctx, profile, body_mass_kg, settings)
    plan = plan_route(ctx.graph, query, (settings.capacities or {}).get(profile.value),
                      settings.reserve_margin, resources_of)
    visited = [(start.lon, start.lat), *((dests[i].lon, dests[i].lat) for i in plan.stop_order)]
    if end:
        visited.append((end.lon, end.lat))
    warnings = [*plan.warnings, *weather_warnings(weather, req.season, visited),
                *([mass_warning] if mass_warning else [])]
    return to_response(ctx, plan, req, start, dests, end, warnings, mass_used)


def to_response(ctx: RoutingContext, plan: RoutePlan, req: RouteRequest, start: SnappedNode,
                dests: list[SnappedNode], end: SnappedNode | None, warnings: list[str],
                body_mass_kg: float | None = None) -> RouteResponse:
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
        body_mass_kg=body_mass_kg,
    )
