"""Make sure a graph that matches the configuration exists, then load it (blocking)."""
from __future__ import annotations

from app.graph.build import BuildConfig
from app.graph.loader import RoutingContext, build_routing_context
from app.graph.startup.lock import DEFAULT_TIMEOUT_S, graph_lock
from app.graph.store import ensure_graph
from app.layers.base import LayerUnavailable
from app.layers.contracts import LayerDataError
from app.layers.inputs.load import load_all
from app.routing.profiles import models_from_settings

DATA_FIX = "Download the data with `python scripts/download_data.py`, then restart."


def prepare_routing_context(settings, lock_timeout_s: float = DEFAULT_TIMEOUT_S) -> tuple[RoutingContext, bool]:
    """(context, built): the saved graph when it is fresh, else a newly built and saved one.

    Fresh means the grid, the profile parameters, the build options and the hashes of the source files all match
    the current configuration and data (`app.graph.store.ensure_graph`). Inside one lock, so that several workers
    starting together build once and the others load the result. Raises LayerUnavailable (HTTP 503) with the fix
    when the data is missing or the build fails.
    """
    try:
        inputs = load_all(settings)
        models = models_from_settings(settings)
        with graph_lock(settings.graph_file, lock_timeout_s):
            data, built = ensure_graph(settings.graph_file, inputs, models, BuildConfig())
        return build_routing_context(data), built
    except LayerDataError as ex:
        raise LayerUnavailable(f"The routing graph cannot be built: {ex.message}", DATA_FIX) from ex
    except LayerUnavailable:
        raise
    except Exception as ex:  # noqa: BLE001 - any build failure becomes a 503 that says why
        raise LayerUnavailable(f"The routing graph could not be built: {ex}",
                               "Check the data and configuration, then run `python -m app.graph` to see the error.") from ex
