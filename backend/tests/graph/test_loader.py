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


# ------------------------------------------------------------------ is the saved graph still the one the config describes?
def _fresh_context(settings):
    from app.graph.build import build_graph
    from app.graph.loader import build_routing_context
    from app.layers.inputs.load import load_all
    from app.routing.profiles import models_from_settings
    return build_routing_context(build_graph(load_all(settings), models_from_settings(settings)))


def test_a_graph_built_from_the_current_configuration_has_no_warnings(fixture_settings):
    from app.graph.loader import staleness_warnings
    assert staleness_warnings(_fresh_context(fixture_settings), fixture_settings) == []


def test_changed_profile_parameters_make_the_graph_stale(fixture_settings):
    from dataclasses import replace
    from app.graph.loader import staleness_warnings
    ctx = _fresh_context(fixture_settings)
    changed = replace(fixture_settings, profiles={"astronaut": {"suit_mass_kg": 99.0}})
    warnings = staleness_warnings(ctx, changed)
    assert len(warnings) == 1 and "other profile parameters" in warnings[0] and "python -m app.graph" in warnings[0]


def test_a_changed_rsl_buffer_makes_the_graph_stale(fixture_settings):
    from dataclasses import replace
    from app.graph.loader import staleness_warnings
    ctx = _fresh_context(fixture_settings)
    warnings = staleness_warnings(ctx, replace(fixture_settings, rsl_buffer_m=750.0))
    assert len(warnings) == 1 and "RSL buffer" in warnings[0] and "python -m app.graph" in warnings[0]


def test_a_different_grid_makes_the_graph_stale(fixture_settings):
    from dataclasses import replace
    from app.graph.loader import staleness_warnings
    ctx = _fresh_context(fixture_settings)
    warnings = staleness_warnings(ctx, replace(fixture_settings, grid_coarsen=2))
    assert len(warnings) == 1 and "grid" in warnings[0] and "grid.coarsen = 2" in warnings[0]


def test_both_problems_are_reported_together(fixture_settings):
    from dataclasses import replace
    from app.graph.loader import staleness_warnings
    both = replace(fixture_settings, grid_coarsen=2, profiles={"car": {"crew_n": 4}})
    assert len(staleness_warnings(_fresh_context(fixture_settings), both)) == 2


def test_the_app_logs_a_stale_graph_once_at_startup(fixture_settings, tmp_path, caplog):
    from dataclasses import replace
    import shutil
    from fastapi.testclient import TestClient
    from main import create_app

    from app.graph.build import build_graph
    from app.layers.inputs.load import load_all
    root = tmp_path / "data"
    shutil.copytree(fixture_settings.data_dir / "raw", root / "raw")
    from app.routing.profiles import models_from_settings
    base = replace(fixture_settings, data_dir=root)
    build_graph(load_all(base), models_from_settings(base)).save(base.graph_file)
    stale = replace(base, profiles={"astronaut": {"suit_mass_kg": 99.0}})
    with caplog.at_level("WARNING", logger="main"):
        with TestClient(create_app(stale)):
            pass
    assert sum("other profile parameters" in r.message for r in caplog.records) == 1
