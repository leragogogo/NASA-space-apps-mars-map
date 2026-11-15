import threading
from dataclasses import replace

import pytest

from app.core.config import Settings
from app.graph.contracts import GraphData
from app.graph.loader import RoutingContext
from app.graph.startup import prepare_routing_context
from app.layers.base import LayerUnavailable
from tests.integration.helpers import make_gentle_data


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=make_gentle_data(tmp_path / "data"), jwt_secret_key="x")


def leftovers(settings):
    return [p.name for p in settings.graph_file.parent.iterdir() if p.name != settings.graph_file.name]


def test_a_missing_graph_is_built_saved_and_loaded(settings):
    assert not settings.graph_file.exists()
    ctx, built = prepare_routing_context(settings)
    assert built is True and isinstance(ctx, RoutingContext) and ctx.graph.n_edges > 0
    assert settings.graph_file.is_file() and GraphData.read_meta(settings.graph_file)["formula_version"]
    assert leftovers(settings) == []  # no lock file and no temporary file left behind


def test_a_fresh_graph_is_reused_not_rebuilt(settings):
    prepare_routing_context(settings)
    stamp = settings.graph_file.stat().st_mtime_ns
    ctx, built = prepare_routing_context(settings)
    assert built is False and ctx.graph.n_edges > 0 and settings.graph_file.stat().st_mtime_ns == stamp


def test_a_changed_profile_parameter_rebuilds(settings):
    prepare_routing_context(settings)
    changed = replace(settings, profiles={"astronaut": {"suit_mass_kg": 99.0}})
    _, built = prepare_routing_context(changed)
    assert built is True
    assert prepare_routing_context(changed)[1] is False  # and the new graph is then fresh for the new config


def test_a_changed_grid_rebuilds(settings):
    prepare_routing_context(settings)
    ctx, built = prepare_routing_context(replace(settings, grid_coarsen=2))
    assert built is True and ctx.grid.nrows == 3


def test_changed_source_data_rebuilds(settings):
    prepare_routing_context(settings)
    weather = settings.raw_dir / "weather" / "context_weather_frames.geojson"
    weather.write_text(weather.read_text().replace("fixture", "fixture!"))  # any change to a source file
    assert prepare_routing_context(settings)[1] is True


def test_missing_data_is_a_503_with_the_fix(tmp_path):
    with pytest.raises(LayerUnavailable) as ex:
        prepare_routing_context(Settings(data_dir=tmp_path))
    assert "cannot be built" in ex.value.detail and "download_data.py" in ex.value.fix


def test_a_failing_build_is_a_503_that_says_why(settings, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("elevation grid has holes")
    monkeypatch.setattr("app.graph.store.build_graph", boom)
    with pytest.raises(LayerUnavailable, match="elevation grid has holes"):
        prepare_routing_context(settings)
    assert leftovers(settings) == []  # the lock is released even though the build failed


def test_workers_starting_together_build_once(settings, monkeypatch):
    import app.graph.store as store
    real, builds = store.build_graph, []
    monkeypatch.setattr(store, "build_graph", lambda *a, **k: (builds.append(1), real(*a, **k))[1])
    results = []
    threads = [threading.Thread(target=lambda: results.append(prepare_routing_context(settings))) for _ in range(4)]
    [t.start() for t in threads]
    [t.join(120) for t in threads]
    assert len(results) == 4 and len(builds) == 1  # one built, three waited and loaded the result
    assert sorted(built for _, built in results) == [False, False, False, True]
    assert leftovers(settings) == []
