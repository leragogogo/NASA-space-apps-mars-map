"""Per-user resource estimates for a route that is already chosen.

The route cost does not depend on body mass (it cancels in the cost formula), so everyone gets the same path.
Oxygen, CO2 and cooling water do depend on it: after the search, the resources of the returned path are
recomputed with the requesting user's mass. Only the edges of the path are touched (thousands, not millions),
and the formula is `AstronautModel.resources`, the same one the graph builder uses.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from app.core.resources import RESOURCES, ProfileId
from app.graph.attrs import combined_formula_version
from app.graph.geometry import edge_geometry
from app.routing.graph import RoutingGraph
from app.routing.profiles import AstronautModel, models_from_settings


def reference_models(settings) -> Mapping[ProfileId, object]:
    """The profile models of the current configuration, which the graph should have been built with."""
    return {m.profile_id: m for m in models_from_settings(settings)}


def graph_matches_models(graph_formula_version: str, models: Mapping[ProfileId, object]) -> bool:
    """False when the saved graph was built with other formulas or parameters than the current models:
    then a request-time recomputation would not be comparable with the graph's own numbers."""
    return graph_formula_version == combined_formula_version(list(models.values()))


def supports_body_mass(profile: ProfileId | str) -> bool:
    return ProfileId(profile) == ProfileId.ASTRONAUT


def path_resources_for_mass(graph: RoutingGraph, model: AstronautModel, nodes: Sequence[int],
                            body_mass_kg: float) -> dict[str, float]:
    """Total of every resource over the edges of a node path, for an astronaut of `body_mass_kg`."""
    nodes = np.asarray(nodes, dtype=np.int64)
    if nodes.size < 2:
        return {r: 0.0 for r in RESOURCES}
    geom = edge_geometry(graph.grid, graph.elev.reshape(graph.grid.shape), nodes[:-1], nodes[1:])
    per_edge = model.resources(geom, body_mass_kg)
    return {r: float(per_edge[r].sum()) for r in RESOURCES}
