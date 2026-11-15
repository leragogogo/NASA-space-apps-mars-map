import pytest

from app.core.config import Settings
from app.graph.loader import load_routing_context
from app.layers.base import LayerUnavailable
from tests.routing.helpers import both, make_graph_data


def test_missing_file_is_unavailable_with_fix(tmp_path):
    with pytest.raises(LayerUnavailable) as ex:
        load_routing_context(Settings(data_dir=tmp_path))
    assert "graph.npz" in ex.value.detail and ex.value.fix


def test_corrupt_file_is_unavailable(tmp_path):
    (tmp_path / "graph").mkdir()
    (tmp_path / "graph" / "graph.npz").write_bytes(b"not a graph")
    with pytest.raises(LayerUnavailable):
        load_routing_context(Settings(data_dir=tmp_path))


def test_loads_saved_graph(tmp_path):
    data = make_graph_data(3, both(0, 1, 1.0) + both(1, 2, 1.0))
    data.save(tmp_path / "graph" / "graph.npz")
    ctx = load_routing_context(Settings(data_dir=tmp_path))
    assert ctx.graph.n_nodes == 3 and ctx.graph.n_edges == 4
    assert ctx.tree.n == 3 and ctx.formula_version == "test"
