"""Step 6: persistence. Save/load `graph.npz` and rebuild only when it is stale.

A saved graph is fresh when its stored fingerprint (format version, grid, profile formula versions,
source file hashes, build parameters) equals the one the current inputs would produce.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from app.core.profiles import ProfileModel
from app.graph.build import REPO_ROOT, BuildConfig, build_graph, expected_fingerprint
from app.graph.contracts import GraphData
from app.layers.contracts import GraphInputs

DEFAULT_GRAPH_PATH = REPO_ROOT / "data" / "graph" / "graph.npz"


def is_fresh(path: Path, expected: dict) -> bool:
    """True if `path` exists, is readable and was built from exactly `expected`."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        meta = GraphData.read_meta(path)
    except Exception:  # corrupt or unreadable file -> rebuild
        return False
    return {k: meta.get(k) for k in expected} == expected


def ensure_graph(path: Path, inputs: GraphInputs, models: Sequence[ProfileModel],
                 config: BuildConfig = BuildConfig(), force: bool = False) -> tuple[GraphData, bool]:
    """Return (graph, built). Loads the saved graph when fresh, otherwise builds and saves it."""
    path = Path(path)
    if not force and is_fresh(path, expected_fingerprint(inputs, models, config)):
        try:
            return GraphData.load(path), False
        except Exception:  # fresh meta but unreadable arrays -> rebuild
            pass
    data = build_graph(inputs, models, config)
    data.save(path)
    return data, True
