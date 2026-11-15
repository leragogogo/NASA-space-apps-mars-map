import dataclasses

import numpy as np
import pytest

from app.core.resources import EDGE_ATTRS, PROFILES, attr_key
from app.graph.build import BuildConfig, build_graph, expected_fingerprint, hash_sources
from app.graph.nodes import build_node_table, weather_conf_key, weather_risk_key
from app.layers.contracts import SEASONS, Confidence, LayerDataError, RiskLevel
from app.layers.fakes import fake_grid, fake_inputs, fake_relief, fake_weather
from app.layers.relief.slope import slope_deg
from tests.graph.stubs import stub_models


def small_inputs(kind="ramp"):
    return fake_inputs(fake_grid(8, 10), relief_kind=kind)


def test_node_table_has_required_and_per_season_arrays():
    inputs = small_inputs()
    node = build_node_table(inputs)
    n = inputs.grid.n_nodes
    for name in ("lon", "lat", "elev_m", "valid", "slope_deg", "nearest_poi_dist_m", "nearest_poi_id"):
        assert node[name].shape == (n,), name
    for k in range(len(SEASONS)):
        assert node[weather_risk_key(k)].shape == (n,) and node[weather_conf_key(k)].dtype == np.int8
    assert weather_risk_key(2) == "weather_risk_2" and weather_conf_key(3) == "weather_conf_3"
    assert np.isnan(node["nearest_poi_dist_m"]).all() and (node["nearest_poi_id"] == -1).all()
    assert "roughness_m" not in node


def test_node_table_is_in_node_id_order_and_does_not_alias_inputs():
    inputs = small_inputs("bowl")
    node = build_node_table(inputs)
    g = inputs.grid
    r, c = 3, 7
    nid = int(g.node_id(r, c))
    assert node["elev_m"][nid] == inputs.relief.elev_m[r, c]
    assert node["lon"][nid] == pytest.approx(g.lon_centers()[c]) and node["lat"][nid] == pytest.approx(g.lat_centers()[r])
    node["elev_m"][0] = 12345.0
    assert inputs.relief.elev_m[0, 0] != 12345.0


def test_node_table_carries_weather_per_season():
    g = fake_grid(8, 10)
    inputs = fake_inputs(g)
    weather = fake_weather(g, by_season={SEASONS[1]: (RiskLevel.HIGH, Confidence.APPROXIMATE)})
    node = build_node_table(dataclasses.replace(inputs, weather=weather))
    assert (node[weather_risk_key(1)] == int(RiskLevel.HIGH)).all()
    assert (node[weather_conf_key(1)] == int(Confidence.APPROXIMATE)).all()
    assert (node[weather_risk_key(0)] == int(RiskLevel.LOW)).all()


def test_build_graph_produces_valid_graph_data():
    inputs = small_inputs()
    g = build_graph(inputs, stub_models())
    g.validate()
    assert g.grid == inputs.grid and g.formula_version == "astronaut=stub-1;car=stub-1"
    assert g.build_params == {"neighbours": 8} and g.source_hashes == {}
    rows, cols = inputs.grid.shape
    assert g.n_edges == 2 * (rows * (cols - 1) + cols * (rows - 1) + 2 * (rows - 1) * (cols - 1))
    assert set(g.edge_arrays) == {attr_key(p, a) for p in PROFILES for a in EDGE_ATTRS}


def test_nodata_cells_become_isolated_nodes():
    inputs = small_inputs("flat")
    elev = inputs.relief.elev_m.copy()
    valid = inputs.relief.valid.copy()
    elev[2, 3] = np.nan
    valid[2, 3] = False
    relief = dataclasses.replace(inputs.relief, elev_m=elev, valid=valid, slope_deg=slope_deg(elev, inputs.grid))
    g = build_graph(dataclasses.replace(inputs, relief=relief), stub_models())
    nid = int(inputs.grid.node_id(2, 3))
    assert nid not in g.src and nid not in g.dst
    assert not g.node["valid"][nid] and np.isnan(g.node["elev_m"][nid])


def test_invalid_inputs_are_rejected_before_building():
    inputs = small_inputs()
    elev = inputs.relief.elev_m.copy()
    elev[0, 0] = np.nan  # but valid[0, 0] is still True
    bad = dataclasses.replace(inputs, relief=dataclasses.replace(inputs.relief, elev_m=elev))
    with pytest.raises(LayerDataError):
        build_graph(bad, stub_models())


def test_four_neighbourhood_has_fewer_edges():
    inputs = small_inputs()
    g8 = build_graph(inputs, stub_models(), BuildConfig(neighbours=8))
    g4 = build_graph(inputs, stub_models(), BuildConfig(neighbours=4))
    assert g4.n_edges < g8.n_edges and g4.build_params == {"neighbours": 4}


def test_source_hashes_and_fingerprint(tmp_path):
    (tmp_path / "dem.tif").write_bytes(b"abc")
    inputs = small_inputs()
    inputs = dataclasses.replace(inputs, relief=dataclasses.replace(inputs.relief, source_files=("dem.tif",)))
    cfg = BuildConfig(repo_root=tmp_path)
    g = build_graph(inputs, stub_models(), cfg)
    assert g.source_hashes == hash_sources(["dem.tif"], tmp_path) and len(g.source_hashes["dem.tif"]) == 64
    assert g.fingerprint() == expected_fingerprint(inputs, stub_models(), cfg)
    (tmp_path / "dem.tif").write_bytes(b"changed")
    assert expected_fingerprint(inputs, stub_models(), cfg) != g.fingerprint()
    with pytest.raises(FileNotFoundError):
        hash_sources(["missing.tif"], tmp_path)


def test_fingerprint_changes_with_formula_version_and_neighbours():
    inputs = small_inputs()
    base = expected_fingerprint(inputs, stub_models())
    models = stub_models()
    models[0].formula_version = "stub-2"
    assert expected_fingerprint(inputs, models) != base
    assert expected_fingerprint(inputs, stub_models(), BuildConfig(neighbours=4)) != base
