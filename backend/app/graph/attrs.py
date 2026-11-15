"""Step 3: apply every profile's cost formulas to the edge geometry.

Produces the `<profile>__<attr>` arrays stored in GraphData.edge_arrays. `cost` is float64 (the
solver sums many of them); the resources are float32. Impassable for a profile means `cost` and
every resource are inf on that edge, never a mix.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from app.core.profiles import EdgeGeometry, ProfileModel, check_edge_attrs
from app.core.resources import COST, EDGE_ATTRS, PROFILES, RESOURCES, ProfileId, attr_key


def _check_models(models: Sequence[ProfileModel]) -> None:
    ids = [ProfileId(m.profile_id) for m in models]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate profile models: {[i.value for i in ids]}")
    missing = set(PROFILES) - set(ids)
    if missing:
        raise ValueError(f"missing profile models: {sorted(p.value for p in missing)}")


def _check_impassable_consistent(profile: ProfileId, attrs: Mapping[str, np.ndarray]) -> None:
    blocked = np.isinf(attrs[COST])
    for name in RESOURCES:
        if (np.isinf(attrs[name]) != blocked).any():
            raise ValueError(f"{profile.value}.{name}: must be inf exactly where cost is inf (impassable edges)")


def compute_edge_arrays(geom: EdgeGeometry, models: Sequence[ProfileModel]) -> dict[str, np.ndarray]:
    """Return {"<profile>__<attr>": array} for every profile and attribute.

    `models` must contain exactly one ProfileModel per ProfileId.
    """
    _check_models(models)
    out: dict[str, np.ndarray] = {}
    for model in sorted(models, key=lambda m: ProfileId(m.profile_id).value):
        profile = ProfileId(model.profile_id)
        attrs = model.compute_edge_attrs(geom)
        check_edge_attrs(attrs, len(geom))
        _check_impassable_consistent(profile, attrs)
        for name in EDGE_ATTRS:
            dtype = np.float64 if name == COST else np.float32
            out[attr_key(profile, name)] = np.asarray(attrs[name]).astype(dtype)
    return out


def combined_formula_version(models: Sequence[ProfileModel]) -> str:
    """One string identifying every profile formula, e.g. 'astronaut=v1;car=v1' (stored in the graph)."""
    _check_models(models)
    return ";".join(f"{ProfileId(m.profile_id).value}={m.formula_version}"
                    for m in sorted(models, key=lambda m: ProfileId(m.profile_id).value))
