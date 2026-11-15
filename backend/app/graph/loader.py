"""Startup loader: graph.npz -> RoutingGraph + KD-tree for snapping (SKILL.md section 10, step 2).

The graph is read-only afterwards, so one RoutingContext is shared across requests.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from app.graph.contracts import GraphData
from app.layers.base import LayerUnavailable
from app.layers.contracts import GridSpec
from app.layers.relief.ingest import grid_for
from app.routing.graph import RoutingGraph
from app.routing.profiles.personalize import graph_matches_models, reference_models


def project(lon, lat, lat0: float, radius_m: float) -> np.ndarray:
    """lon/lat -> local metric x/y (lon scaled by cos(lat0)); good enough for nearest-node search."""
    k = math.radians(1.0) * radius_m
    return np.column_stack([np.asarray(lon, dtype=float) * math.cos(math.radians(lat0)) * k,
                            np.asarray(lat, dtype=float) * k])


@dataclass(frozen=True, eq=False)
class RoutingContext:
    graph: RoutingGraph
    grid: GridSpec
    formula_version: str
    tree: cKDTree  # over valid nodes only, in local metres
    valid_ids: np.ndarray  # tree index -> node id
    lat0: float  # reference latitude of the local projection

    def project(self, lon, lat) -> np.ndarray:
        return project(lon, lat, self.lat0, self.grid.radius_m)


def build_routing_context(data: GraphData) -> RoutingContext:
    valid_ids = np.flatnonzero(np.asarray(data.node["valid"], dtype=bool))
    if valid_ids.size == 0:
        raise LayerUnavailable("The routing graph has no valid nodes.", "Rebuild the master graph.")
    lon, lat = np.asarray(data.node["lon"])[valid_ids], np.asarray(data.node["lat"])[valid_ids]
    lat0 = float(lat.mean())
    tree = cKDTree(project(lon, lat, lat0, data.grid.radius_m))
    return RoutingContext(RoutingGraph.from_graph_data(data), data.grid, data.formula_version,
                          tree, valid_ids, lat0)


def staleness_warnings(ctx: RoutingContext, settings) -> list[str]:
    """Why the saved graph no longer matches the current configuration (empty when it does).

    A stale graph still routes, but its costs came from other parameters or another grid than the ones the
    configuration and the map now use. The fix is always `python -m app.graph`.
    """
    warnings = []
    if not graph_matches_models(ctx.formula_version, reference_models(settings)):
        warnings.append("The routing graph was built with other profile parameters than the current configuration "
                        "(config/mars.yaml): route costs and the per-user estimates do not match it. "
                        "Rebuild it with `python -m app.graph`.")
    wanted = grid_for(settings)
    if ctx.grid != wanted:
        warnings.append(f"The routing graph is on a {ctx.grid.nrows} x {ctx.grid.ncols} grid but the configuration "
                        f"(grid.coarsen = {settings.grid_coarsen}) gives {wanted.nrows} x {wanted.ncols}: the map and "
                        "the router disagree. Rebuild it with `python -m app.graph`.")
    return warnings


def load_routing_context(settings) -> RoutingContext:
    """Raises LayerUnavailable (-> HTTP 503) when graph.npz is missing or unreadable."""
    path = settings.graph_file
    if not path.is_file():
        raise LayerUnavailable(f"Routing graph not found: {path}",
                               "Build the master graph (app/graph/build.py) so that data/graph/graph.npz exists.")
    try:
        return build_routing_context(GraphData.load(path))
    except LayerUnavailable:
        raise
    except Exception as ex:  # corrupt / outdated file
        raise LayerUnavailable(f"Routing graph {path} could not be loaded: {ex}", "Rebuild the master graph.")
