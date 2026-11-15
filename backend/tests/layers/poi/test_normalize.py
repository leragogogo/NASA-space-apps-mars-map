from app.layers.poi.normalize import CATEGORIES, DATASETS, normalize_feature, normalize_lon


def feat(lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def test_categories():
    assert CATEGORIES == ("mineral", "water_activity", "exploration_zone", "dunes", "geology", "place_name",
                          "observation")
    assert len(DATASETS) == 10


def test_normalize_lon_nested():
    assert normalize_lon([290.0, -11.0]) == [-70.0, -11.0]
    assert normalize_lon([[[-70.0, -12.0], [300.0, -12.0]]]) == [[[-70.0, -12.0], [-60.0, -12.0]]]


def test_mineral_mapping_and_id():
    f = normalize_feature("Aquieous_Mineral_Distribution_Options_clon0__0", 5, feat(-70, -12, FID=3, Class="sulfate"))
    p = f["properties"]
    assert (p["id"], p["category"], p["name"]) == ("Aquieous_Mineral_Distribution_Options_clon0__0:3", "mineral",
                                                   "Sulfate detection")
    assert p["raw"]["Class"] == "sulfate" and p["source"]


def test_id_falls_back_to_index():
    f = normalize_feature("Dune_Field__0", 7, feat(-70, -12, Dune_ID="2886-131", Dune_Type="Bd, L"))
    assert f["properties"]["id"] == "Dune_Field__0:7"
    assert f["properties"]["name"] == "Dune field 2886-131"


def test_other_mappings():
    cases = {
        "RSLs_Gullies_New_IcyCraters_clon0__0": ({"Type": "confirmed recurring slope lineae (RSL)"},
                                                 "water_activity", "Confirmed recurring slope lineae (RSL)"),
        "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0__0": ({"Instrument": "CRISM"}, "mineral",
                                                            "Hydrous mineral detection"),
        "EZMars__0": ({"name": "Melas Chasma"}, "exploration_zone", "Melas Chasma exploration zone (centre)"),
        "EZMars__3": ({"name": "1007.03", "ez_name": "Melas Chasma"}, "exploration_zone", "Melas Chasma ROI 1007.03"),
        "EZMars__4": ({"name": "Coprates Chasma"}, "exploration_zone", "Coprates Chasma exploration zone boundary"),
        "SIM3292_Global_Geology__0": ({"Unit": "Aa", "UnitDesc": "Amazonian apron unit"}, "geology",
                                      "Amazonian apron unit (Aa)"),
        "combinedNom__0": ({"name": "Garni", "type": "Crater, craters"}, "place_name", "Garni"),
        "mars_mro_crism_mtrdr_c0a_humex_frt_sites__0": ({"ProductId": "FRT0000B64A_07_IF164J_MTR3",
                                                         "UTCstart": "2008-07-06T21:31:41.032"}, "observation",
                                                        "CRISM observation FRT0000B64A_07_IF164J_MTR3"),
    }
    for stem, (props, cat, name) in cases.items():
        p = normalize_feature(stem, 0, feat(-70, -12, **props))["properties"]
        assert (p["category"], p["name"]) == (cat, name), stem
        assert p["description"], stem


def test_null_geometry_kept():
    f = normalize_feature("combinedNom__0", 0, {"type": "Feature", "geometry": None, "properties": {"name": "X"}})
    assert f["geometry"] is None
