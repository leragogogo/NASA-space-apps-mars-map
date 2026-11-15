import pytest
from shapely.geometry import shape

from app.layers.poi.ingest import ingest_poi
from app.layers.poi.service import PoiGetter
from app.tiles.store import TileStore


def make(settings):
    return PoiGetter(settings, TileStore(settings.raw_dir / "tiles", settings.tile_sources, settings.aoi),
                     ingest_poi(settings))


@pytest.fixture(scope="module")
def poi(fixture_settings):
    return make(fixture_settings)


def test_loads_known_files_only(poi):
    feats = poi.features()
    assert len(feats) == 7  # unknown_dataset__0 is skipped
    assert all(f["properties"]["category"] for f in feats)


def test_describe_counts_and_overlay(poi):
    d = poi.describe()
    assert d["type"] == "FeatureCollection" and d["layer"] == "poi"
    assert d["categories"] == {"mineral": 3, "water_activity": 1, "exploration_zone": 1, "dunes": 0,
                               "geology": 1, "place_name": 1, "observation": 0}
    assert [o["id"] for o in d["overlays"]] == ["crism_sulfate"]


def test_category_filter(poi):
    d = poi.describe({"mineral"})
    assert len(d["features"]) == 3
    assert d["categories"]["geology"] == 1  # counts always describe the full set


def test_longitude_normalised(poi):
    silica = next(f for f in poi.features() if f["properties"]["name"] == "Silica detection")
    assert silica["geometry"]["coordinates"] == [-70.0, -11.0]


def test_geology_clipped_to_aoi(poi):
    geo = next(f for f in poi.features() if f["properties"]["category"] == "geology")
    w, s, e, n = shape(geo["geometry"]).bounds
    assert (w, s, e, n) == pytest.approx((-71.8, -13.4, -70.0, -11.0))


def test_sample_radius(poi):
    near = poi.sample(-70.0, -12.0)
    ids = [x["id"] for x in near]
    assert "Aquieous_Mineral_Distribution_Options_clon0:0:0" in ids
    assert "EZMars:3:0" in ids                     # polygon corner touches the point
    assert "combinedNom:0:0" not in ids            # Garni is ~34 km away
    assert near == sorted(near, key=lambda x: x["distance_km"])


def test_client_features_carry_kind_and_category(poi):
    f = next(f for f in poi.features() if f["properties"]["name"] == "Silica detection")
    assert f["properties"]["kind"] == "mineral_silica" and f["properties"]["category"] == "mineral"
