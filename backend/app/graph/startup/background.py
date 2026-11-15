"""Run the graph preparation in a thread while the API already serves everything else."""
from __future__ import annotations

import logging
import threading
import time

from app.graph.loader import staleness_warnings
from app.graph.startup import prepare as prepare_module
from app.layers.base import LayerUnavailable

log = logging.getLogger(__name__)

BUILDING = LayerUnavailable(
    "The routing graph is being prepared (the first start takes about a minute); try again shortly.",
    "Wait for the build to finish, or run `python -m app.graph` yourself.")


def start_background_build(app, settings) -> threading.Thread:
    """Set `app.state.routing` to a 503 placeholder, prepare the graph in a thread, then swap in the result.

    `/api/route` reads `app.state.routing` on every request, so it starts working the moment the thread finishes.
    The thread is `app.state.routing_task`. A failure leaves the 503, now carrying the reason.
    """
    app.state.routing = BUILDING
    started = time.monotonic()

    def run():
        try:
            ctx, built = prepare_module.prepare_routing_context(settings)
        except LayerUnavailable as ex:
            log.error("Routing graph unavailable: %s (fix: %s)", ex.detail, ex.fix)
            app.state.routing = ex
            return
        for warning in staleness_warnings(ctx, settings):
            log.warning(warning)
        app.state.routing = ctx
        log.info("Routing graph %s in %.0f s", "built and saved" if built else "loaded", time.monotonic() - started)

    thread = threading.Thread(target=run, name="routing-graph-build", daemon=True)
    app.state.routing_task = thread
    thread.start()
    return thread
