import pytest
from shapely.geometry import shape

from app.core.config import Settings
from app.layers.contracts import LayerDataError, PoiData, PoiKind
from app.layers.poi.ingest import ingest_poi
from app.layers.validate import validate_poi


@pytest.fixture(scope="module")
def poi(fixture_settings) -> PoiData:
    return ingest_poi(fixture_settings)


def test_known_files_only_and_valid(poi):
    validate_poi(poi)
    assert len(poi.features) == 7  # unknown_dataset__0 is skipped
    assert len(poi.source_files) == 6 and all(":" in f for f in poi.source_files)


def test_kinds_ids_and_sources(poi):
    by_id = {f.id: f for f in poi.features}
    assert by_id["Aquieous_Mineral_Distribution_Options_clon0:0:0"].kind == PoiKind.MINERAL_SULFATE
    assert by_id["Aquieous_Mineral_Distribution_Options_clon0:0:1"].kind == PoiKind.MINERAL_SILICA
    assert by_id["Hydrous_Mineral_Detections_OMEGA_CRISM_clon0:0:0"].kind == PoiKind.MINERAL_HYDROUS
    assert by_id["RSLs_Gullies_New_IcyCraters_clon0:0:0"].kind == PoiKind.RSL
    assert by_id["EZMars:3:0"].kind == PoiKind.EXPLORATION_ROI and by_id["EZMars:3:0"].source == "EZMars/3"
    assert by_id["combinedNom:0:0"].kind == PoiKind.NOMENCLATURE and by_id["combinedNom:0:0"].name == "Garni"


def test_longitude_normalised(poi):
    silica = next(f for f in poi.features if f.kind == PoiKind.MINERAL_SILICA)
    assert silica.geometry["coordinates"] == [-70.0, -11.0] and silica.lonlat() == (-70.0, -11.0)


def test_geology_clipped_to_aoi(poi):
    geo = next(f for f in poi.features if f.kind == PoiKind.GEOLOGY_UNIT)
    assert shape(geo.geometry).bounds == pytest.approx((-71.8, -13.4, -70.0, -11.0))


def test_geojson_and_points_helpers(poi):
    assert len(poi.as_geojson(["mineral_sulfate"])["features"]) == 1
    assert ("EZMars:3:0", PoiKind.EXPLORATION_ROI) == poi.points(["exploration_roi"])[0][:2]


def test_missing_features_dir(tmp_path):
    with pytest.raises(LayerDataError) as ex:
        ingest_poi(Settings(data_dir=tmp_path))
    assert "--only pois" in ex.value.message
