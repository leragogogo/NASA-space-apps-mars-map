import pytest
from shapely.geometry import shape

from app.core.config import Settings
from app.layers.base import LayerUnavailable
from app.layers.poi.getter import PoiGetter
from app.tiles.store import TileStore


def make(settings):
    return PoiGetter(settings, TileStore(settings.raw_dir / "tiles", settings.tile_sources, settings.aoi))


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
    assert "Aquieous_Mineral_Distribution_Options_clon0__0:0" in ids
    assert "EZMars__3:0" in ids                     # polygon corner touches the point
    assert "combinedNom__0:0" not in ids            # Garni is ~34 km away
    assert near == sorted(near, key=lambda x: x["distance_km"])


def test_missing_features_dir(tmp_path):
    with pytest.raises(LayerUnavailable) as ex:
        make(Settings(data_dir=tmp_path))
    assert "--only pois" in ex.value.fix
