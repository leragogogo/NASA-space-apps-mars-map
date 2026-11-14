"""GraphData: the master graph as plain arrays (struct-of-arrays), the contract between the
graph builder (writes it), the loader (reads it, builds the rustworkx graph) and routing.

Logical view of one edge (see edge_attrs):
    {"astronaut": {"cost": .., "o2_g": .., ...}, "car": {...}}
Physical storage: one array per (profile, attribute), named "<profile>__<attr>". Never a dict
per edge. Spec: context/skills/mars-mvp-data/references/edge-cost-model.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import numpy as np

from app.core.resources import EDGE_ATTRS, PROFILES, ProfileId, attr_key
from app.layers.contracts import GridSpec

NODE_REQUIRED = ("lon", "lat", "elev_m", "valid")
_META_KEY = "__meta__"
_NODE_PREFIX = "node__"


@dataclass(frozen=True, eq=False)
class GraphData:
    grid: GridSpec
    node: Mapping[str, np.ndarray]  # each length grid.n_nodes; must include NODE_REQUIRED
    src: np.ndarray  # int, length m, node ids
    dst: np.ndarray
    edge_arrays: Mapping[str, np.ndarray]  # "<profile>__<attr>" -> float array length m
    formula_version: str
    source_hashes: Mapping[str, str] = field(default_factory=dict)

    @property
    def n_edges(self) -> int:
        return int(self.src.shape[0])

    def array(self, profile: ProfileId | str, attr: str) -> np.ndarray:
        return self.edge_arrays[attr_key(profile, attr)]

    def cost(self, profile: ProfileId | str) -> np.ndarray:
        return self.array(profile, "cost")

    def edge_attrs(self, edge_id: int) -> dict[str, dict[str, float]]:
        """Logical dict view of one edge, for the API, debugging and tests."""
        return {p.value: {a: float(self.array(p, a)[edge_id]) for a in EDGE_ATTRS} for p in PROFILES}

    def validate(self) -> None:
        problems: list[str] = []
        n, m = self.grid.n_nodes, self.n_edges
        for name in NODE_REQUIRED:
            if name not in self.node:
                problems.append(f"node array {name!r} missing")
        for name, arr in self.node.items():
            if arr.shape != (n,):
                problems.append(f"node.{name}: shape {arr.shape} != ({n},)")
        if self.dst.shape != (m,):
            problems.append("src and dst must have the same length")
        elif m and (min(self.src.min(), self.dst.min()) < 0 or max(self.src.max(), self.dst.max()) >= n):
            problems.append("src/dst contain node ids outside the grid")
        for p in PROFILES:
            for a in EDGE_ATTRS:
                key = attr_key(p, a)
                arr = self.edge_arrays.get(key)
                if arr is None:
                    problems.append(f"{key}: missing")
                    continue
                if arr.shape != (m,):
                    problems.append(f"{key}: shape {arr.shape} != ({m},)")
                elif np.isnan(arr).any() or (arr < 0).any():
                    problems.append(f"{key}: contains NaN or negative values (inf is allowed)")
        extra = set(self.edge_arrays) - {attr_key(p, a) for p in PROFILES for a in EDGE_ATTRS}
        if extra:
            problems.append(f"unexpected edge arrays: {sorted(extra)}")
        if not self.formula_version:
            problems.append("formula_version must not be empty")
        if problems:
            raise ValueError("invalid GraphData: " + "; ".join(problems))

    def save(self, path: str | Path) -> None:
        self.validate()
        meta = {"grid": self.grid.to_dict(), "formula_version": self.formula_version,
                "source_hashes": dict(self.source_hashes)}
        arrays = {f"{_NODE_PREFIX}{k}": v for k, v in self.node.items()}
        arrays.update(src=self.src, dst=self.dst, **self.edge_arrays)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **arrays, **{_META_KEY: np.array(json.dumps(meta))})

    @classmethod
    def load(cls, path: str | Path) -> "GraphData":
        with np.load(path, allow_pickle=False) as z:
            meta = json.loads(str(z[_META_KEY]))
            node = {k[len(_NODE_PREFIX):]: z[k] for k in z.files if k.startswith(_NODE_PREFIX)}
            edge_keys = {attr_key(p, a) for p in PROFILES for a in EDGE_ATTRS}
            edge_arrays = {k: z[k] for k in z.files if k in edge_keys}
            data = cls(grid=GridSpec.from_dict(meta["grid"]), node=node, src=z["src"], dst=z["dst"],
                       edge_arrays=edge_arrays, formula_version=meta["formula_version"],
                       source_hashes=meta.get("source_hashes", {}))
        data.validate()
        return data
