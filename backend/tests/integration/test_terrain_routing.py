"""Terrain-aware routing end to end: fake layers -> graph (map slope, hazards) -> request with profile "auto"."""
from app.core.config import Settings
from app.graph.build import build_graph
from app.graph.loader import build_routing_context
from app.layers.contracts import GraphInputs, PoiData, PoiFeature, PoiKind
from app.layers.fakes import fake_grid, fake_relief, fake_weather
from app.routing.profiles import default_models
from app.routing.request import handle_route_request
from app.schemas.route import RouteRequest

GRID = fake_grid(24, 30)


def context(relief_kind="flat", poi=(), **relief_kw):
    inputs = GraphInputs(grid=GRID, relief=fake_relief(GRID, relief_kind, **relief_kw), weather=fake_weather(GRID),
                         poi=PoiData(features=tuple(poi)))
    return build_routing_context(build_graph(inputs, default_models()))


def point(row, col):
    return {"lon": float(GRID.lon_centers()[col]), "lat": float(GRID.lat_centers()[row])}


def route(ctx, start, end):
    return handle_route_request(ctx, RouteRequest(start=start, end=end, time_limit_s=1), Settings())


def test_a_hillside_too_steep_to_walk_is_driven_even_along_the_contour():
    ctx = context("ramp", slope_deg_=22.0)  # rises to the east: a north-south move is level but crosses 22 deg
    d = route(ctx, point(3, 10), point(20, 10))
    walking = next(o for o in d.mode.options if o.profile == "astronaut")
    car = next(o for o in d.mode.options if o.profile == "car")
    assert d.profile == "car" and car.feasible and not walking.feasible
    assert walking.reason and "passable for the astronaut" in walking.reason


def test_a_dune_band_blocks_the_car_so_auto_walks():
    w = float(GRID.lon_centers()[14] - GRID.dlon / 2)
    e = float(GRID.lon_centers()[15] + GRID.dlon / 2)
    s, n = GRID.south - 1, GRID.north + 1
    band = PoiFeature(id="t:0:0", kind=PoiKind.DUNE_FIELD, source="t/0",
                      geometry={"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]})
    d = route(context(poi=[band]), point(12, 5), point(12, 25))
    car = next(o for o in d.mode.options if o.profile == "car")
    walking = next(o for o in d.mode.options if o.profile == "astronaut")
    assert d.profile == "astronaut" and walking.feasible and not car.feasible


def test_on_open_flat_ground_auto_picks_the_mode_with_less_oxygen_per_person():
    d = route(context(), point(12, 5), point(12, 9))
    assert all(o.feasible for o in d.mode.options)
    assert len({o.o2_g for o in d.mode.options}) == 2
    assert d.mode.chosen == min(d.mode.options, key=lambda o: o.o2_g).profile
