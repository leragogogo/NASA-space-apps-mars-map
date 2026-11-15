"""Step 5: build the master graph (GraphData) from the layer ingestion output.

    inputs (GraphInputs) -> validate -> edges -> geometry -> per-profile cost/resources -> node table

Never reads data/raw/ directly: only `inputs` and the profile models. Pure given its arguments, so
it is tested with fake inputs and stub profiles.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.core.profiles import ProfileModel
from app.graph.attrs import combined_formula_version, compute_edge_arrays
from app.graph.contracts import GraphData, make_fingerprint
from app.graph.edges import enumerate_edges
from app.graph.geometry import edge_geometry
from app.graph.nodes import build_node_table
from app.layers.contracts import GraphInputs
from app.layers.validate import validate_inputs

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class BuildConfig:
    neighbours: int = 8  # 4 or 8
    repo_root: Path = REPO_ROOT  # `source_files` of the layers are relative to this

    def params(self) -> dict:
        return {"neighbours": self.neighbours}


def hash_sources(source_files: Sequence[str], root: Path) -> dict[str, str]:
    """sha256 of every source file (relative to root): the provenance stored in the graph."""
    out = {}
    for rel in sorted(set(source_files)):
        path = Path(root) / rel
        if not path.is_file():
            raise FileNotFoundError(f"source file {rel!r} listed by a layer does not exist under {root}")
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _all_sources(inputs: GraphInputs) -> list[str]:
    return [*inputs.relief.source_files, *inputs.weather.source_files, *inputs.poi.source_files]


def expected_fingerprint(inputs: GraphInputs, models: Sequence[ProfileModel],
                         config: BuildConfig = BuildConfig()) -> dict:
    """The fingerprint `build_graph` would produce, without building (used to skip rebuilds)."""
    return make_fingerprint(inputs.grid, combined_formula_version(models),
                            hash_sources(_all_sources(inputs), config.repo_root), config.params())


def build_graph(inputs: GraphInputs, models: Sequence[ProfileModel],
                config: BuildConfig = BuildConfig()) -> GraphData:
    validate_inputs(inputs)  # raises LayerDataError listing every problem
    grid, relief = inputs.grid, inputs.relief
    src, dst = enumerate_edges(grid, relief.valid, config.neighbours)
    geom = edge_geometry(grid, relief.elev_m, src, dst, relief.roughness_m)
    data = GraphData(
        grid=grid, node=build_node_table(inputs), src=src, dst=dst,
        edge_arrays=compute_edge_arrays(geom, models),
        formula_version=combined_formula_version(models),
        source_hashes=hash_sources(_all_sources(inputs), config.repo_root),
        build_params=config.params())
    data.validate()
    return data
