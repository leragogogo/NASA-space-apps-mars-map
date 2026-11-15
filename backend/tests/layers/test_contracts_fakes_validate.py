import dataclasses

import numpy as np
import pytest

from app.layers.contracts import (SEASONS, Confidence, GraphInputs, ImageryCatalog, ImageryLayerInfo,
                                  LayerDataError, PoiData, PoiFeature, PoiKind, RiskLevel)
from app.layers.fakes import RELIEF_KINDS, fake_grid, fake_inputs, fake_poi, fake_relief, fake_weather
from app.layers.validate import validate_inputs, validate_poi, validate_relief, validate_weather


@pytest.mark.parametrize("kind", RELIEF_KINDS)
def test_every_fake_relief_validates(kind):
    validate_relief(fake_relief(fake_grid(), kind))


def test_fake_inputs_validate_end_to_end():
    validate_inputs(fake_inputs())


def test_relief_validation_catches_problems():
    r = fake_relief(fake_grid(), "flat")
    nan_elev = r.elev_m.copy()
    nan_elev[0, 0] = np.nan  # but valid[0,0] is still True
    with pytest.raises(LayerDataError, match="NaN exactly where valid is False"):
        validate_relief(dataclasses.replace(r, elev_m=nan_elev))
    with pytest.raises(LayerDataError, match="shape"):
        validate_relief(dataclasses.replace(r, slope_deg=r.slope_deg[:-1]))
    with pytest.raises(LayerDataError, match="float32"):
        validate_relief(dataclasses.replace(r, elev_m=r.elev_m.astype(np.float64)))


def test_poi_geojson_filter_points_and_validation():
    g = fake_grid()
    poi = fake_poi(g, n=8)
    validate_poi(poi, g)
    gj = poi.as_geojson(kinds=[PoiKind.RSL])
    assert gj["type"] == "FeatureCollection" and gj["features"]
    assert all(f["properties"]["kind"] == "rsl" for f in gj["features"])
    assert all(g.contains(lon, lat) for _, _, lon, lat in poi.points())
    bad = PoiData(features=(PoiFeature("x", PoiKind.RSL, {"type": "Point", "coordinates": [250.0, -11.0]}, "s/0"),))
    with pytest.raises(LayerDataError, match="out of range"):
        validate_poi(bad)
    dup = PoiData(features=poi.features + poi.features[:1])
    with pytest.raises(LayerDataError, match="duplicate"):
        validate_poi(dup)


def test_polygon_representative_point():
    ring = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]
    f = PoiFeature("p", PoiKind.EXPLORATION_ROI, {"type": "Polygon", "coordinates": [ring]}, "s/0")
    lon, lat = f.lonlat()
    assert 0 < lon < 2 and 0 < lat < 2
    with pytest.raises(ValueError):
        PoiFeature("q", PoiKind.RSL, {"type": "LineString", "coordinates": []}, "s/0").lonlat()


def test_weather_lookup_and_messages():
    g = fake_grid()
    w = fake_weather(g, RiskLevel.LOW, Confidence.RELIABLE,
                     by_season={SEASONS[1]: (RiskLevel.HIGH, Confidence.APPROXIMATE)})
    validate_weather(w)
    lon, lat = g.lon_centers()[3], g.lat_centers()[3]
    assert w.risk_at(lon, lat, SEASONS[0]) == (RiskLevel.LOW, Confidence.RELIABLE)
    assert w.risk_at(lon, lat, SEASONS[1]) == (RiskLevel.HIGH, Confidence.APPROXIMATE)
    assert w.frame_at(lon, lat, SEASONS[1])["message"].startswith("APPROXIMATE")
    assert w.frame_at(0.0, 0.0, SEASONS[0]) is None
    assert w.risk_at(0.0, 0.0, SEASONS[0]) == (RiskLevel.NONE, Confidence.INSUFFICIENT_DATA)
    with pytest.raises(ValueError):
        w.frame_at(lon, lat, "Winter")


def test_weather_validation_catches_problems():
    g = fake_grid()
    w = fake_weather(g)
    bad = w.risk.copy()
    bad[0, 0, 0] = 7
    with pytest.raises(LayerDataError, match="risk values"):
        validate_weather(dataclasses.replace(w, risk=bad))
    with pytest.raises(LayerDataError, match="caveat"):
        validate_weather(dataclasses.replace(w, caveat=" "))
    with pytest.raises(LayerDataError, match="seasons"):
        validate_weather(dataclasses.replace(w, seasons=tuple(reversed(SEASONS))))


def test_graph_inputs_reject_mismatched_grids():
    a, b = fake_grid(10, 10), fake_grid(12, 12)
    with pytest.raises(LayerDataError, match="grid"):
        GraphInputs(grid=a, relief=fake_relief(b), weather=fake_weather(a), poi=fake_poi(a))


def test_imagery_catalog_tile_path(tmp_path):
    info = ImageryLayerInfo("L", "L", "base", 256, "png", 5, 9, (-71.8, -13.4, -68.0, -10.0))
    cat = ImageryCatalog(root=tmp_path, layers=(info,))
    assert cat.tile_path("L", 9, 1, 2) is None
    (tmp_path / "L" / "9" / "1").mkdir(parents=True)
    (tmp_path / "L" / "9" / "1" / "2.png").write_bytes(b"x")
    assert cat.tile_path("L", 9, 1, 2) == tmp_path / "L" / "9" / "1" / "2.png"
    with pytest.raises(KeyError):
        cat.tile_path("missing", 9, 1, 2)
