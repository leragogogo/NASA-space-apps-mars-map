import dataclasses

import numpy as np
import pytest

from app.core.resources import EDGE_ATTRS, PROFILES, attr_key
from app.graph.contracts import GraphData
from app.layers.fakes import fake_grid


def make_graph(m=3):
    grid = fake_grid(2, 3)
    n = grid.n_nodes
    lon, lat = grid.node_lonlat()
    node = {"lon": lon, "lat": lat, "elev_m": np.zeros(n, np.float32), "valid": np.ones(n, bool)}
    edge_arrays = {attr_key(p, a): np.full(m, float(i + 1), dtype=np.float32)
                   for i, p in enumerate(PROFILES) for a in EDGE_ATTRS}
    return GraphData(grid=grid, node=node, src=np.array([0, 1, 2][:m]), dst=np.array([1, 2, 3][:m]),
                     edge_arrays=edge_arrays, formula_version="test-1", source_hashes={"dem": "abc"},
                     build_params={"neighbours": 8})


def test_valid_graph_and_logical_edge_view():
    g = make_graph()
    g.validate()
    assert g.n_edges == 3
    view = g.edge_attrs(1)
    assert set(view) == {"astronaut", "car"}
    assert set(view["astronaut"]) == set(EDGE_ATTRS)
    assert view["astronaut"]["cost"] == 1.0 and view["car"]["o2_g"] == 2.0
    assert g.cost("car")[0] == 2.0


def test_inf_allowed_nan_and_negative_rejected():
    g = make_graph()
    g.array("astronaut", "cost")[0] = np.inf
    g.validate()
    for bad in (np.nan, -1.0):
        g = make_graph()
        g.array("car", "o2_g")[0] = bad
        with pytest.raises(ValueError, match="car__o2_g"):
            g.validate()


def test_missing_attribute_wrong_length_and_bad_node_ids_rejected():
    g = make_graph()
    arrays = dict(g.edge_arrays)
    del arrays["car__energy_wh"]
    with pytest.raises(ValueError, match="car__energy_wh"):
        dataclasses.replace(g, edge_arrays=arrays).validate()
    arrays = dict(g.edge_arrays)
    arrays["astronaut__cost"] = np.ones(2, dtype=np.float32)
    with pytest.raises(ValueError, match="astronaut__cost"):
        dataclasses.replace(g, edge_arrays=arrays).validate()
    with pytest.raises(ValueError, match="outside the grid"):
        dataclasses.replace(g, dst=np.array([1, 2, 99])).validate()
    with pytest.raises(ValueError, match="formula_version"):
        dataclasses.replace(g, formula_version="").validate()


def test_save_load_roundtrip(tmp_path):
    g = make_graph()
    path = tmp_path / "sub" / "graph.npz"
    g.save(path)
    h = GraphData.load(path)
    assert h.grid == g.grid and h.formula_version == "test-1" and h.source_hashes == {"dem": "abc"}
    np.testing.assert_array_equal(h.src, g.src)
    np.testing.assert_array_equal(h.node["lon"], g.node["lon"])
    for key, arr in g.edge_arrays.items():
        np.testing.assert_array_equal(h.edge_arrays[key], arr)
    assert h.edge_attrs(0) == g.edge_attrs(0)


def test_fingerprint_roundtrips_and_read_meta_needs_no_arrays(tmp_path):
    g = make_graph()
    path = tmp_path / "g.npz"
    g.save(path)
    fp = g.fingerprint()
    assert fp["build_params"] == {"neighbours": 8} and fp["source_hashes"] == {"dem": "abc"}
    assert fp["formula_version"] == "test-1" and fp["grid"] == g.grid.to_dict()
    assert GraphData.read_meta(path) == fp
    assert GraphData.load(path).build_params == {"neighbours": 8}


def test_unknown_format_version_is_rejected(tmp_path):
    import json
    g = make_graph()
    path = tmp_path / "g.npz"
    g.save(path)
    with np.load(path) as z:
        arrays = {k: z[k] for k in z.files}
    meta = json.loads(str(arrays["__meta__"]))
    meta["format_version"] = 999
    arrays["__meta__"] = np.array(json.dumps(meta))
    np.savez_compressed(path, **arrays)
    with pytest.raises(ValueError, match="unsupported graph format"):
        GraphData.load(path)
