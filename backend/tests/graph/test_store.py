import dataclasses

from app.graph.build import BuildConfig
from app.graph.store import ensure_graph, is_fresh
from app.graph.build import expected_fingerprint
from app.layers.fakes import fake_grid, fake_inputs
from tests.graph.stubs import stub_models


def test_build_then_reuse_then_rebuild_on_change(tmp_path):
    path = tmp_path / "g" / "graph.npz"
    inputs = fake_inputs(fake_grid(6, 8))
    g1, built1 = ensure_graph(path, inputs, stub_models())
    assert built1 and path.exists()
    g2, built2 = ensure_graph(path, inputs, stub_models())
    assert not built2 and g2.n_edges == g1.n_edges
    models = stub_models()
    models[1].formula_version = "stub-2"
    _, built3 = ensure_graph(path, inputs, models)
    assert built3
    _, built4 = ensure_graph(path, inputs, models, BuildConfig(neighbours=4))
    assert built4


def test_force_rebuilds(tmp_path):
    path = tmp_path / "graph.npz"
    inputs = fake_inputs(fake_grid(6, 8))
    ensure_graph(path, inputs, stub_models())
    _, built = ensure_graph(path, inputs, stub_models(), force=True)
    assert built


def test_grid_change_makes_it_stale(tmp_path):
    path = tmp_path / "graph.npz"
    ensure_graph(path, fake_inputs(fake_grid(6, 8)), stub_models())
    _, built = ensure_graph(path, fake_inputs(fake_grid(7, 8)), stub_models())
    assert built


def test_missing_or_corrupt_file_is_not_fresh_and_gets_rebuilt(tmp_path):
    path = tmp_path / "graph.npz"
    inputs = fake_inputs(fake_grid(6, 8))
    expected = expected_fingerprint(inputs, stub_models())
    assert not is_fresh(path, expected)
    path.write_bytes(b"not an npz")
    assert not is_fresh(path, expected)
    g, built = ensure_graph(path, inputs, stub_models())
    assert built and is_fresh(path, expected)
