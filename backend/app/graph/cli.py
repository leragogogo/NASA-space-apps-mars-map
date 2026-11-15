"""Step 8: `python -m app.graph`: build (or reuse) graph.npz.

    python -m app.graph --fake            build from synthetic layers + stub profiles (dev/demo)
    python -m app.graph --fake --small    ... on a tiny grid (fast)
    python -m app.graph                   the layer getters' data (data/raw/) + the real profile models
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from app.graph.build import BuildConfig
from app.graph.fakes import stub_models
from app.graph.store import DEFAULT_GRAPH_PATH, ensure_graph
from app.layers.contracts import GraphInputs, LayerDataError, default_grid
from app.layers.fakes import fake_grid, fake_poi, fake_relief, fake_weather
from app.core.config import Settings
from app.graph.getters import graph_inputs_from_registry
from app.layers.registry import build_registry
from app.routing.profiles import default_models

FAKE_GRAPH_PATH = DEFAULT_GRAPH_PATH.with_name("graph_fake.npz")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.graph", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fake", action="store_true", help="synthetic layers and stub profile models")
    ap.add_argument("--small", action="store_true", help="with --fake: use a tiny grid")
    ap.add_argument("--out", type=Path, default=None, help=f"default {DEFAULT_GRAPH_PATH} (fake: {FAKE_GRAPH_PATH})")
    ap.add_argument("--data-dir", type=Path, default=None, help="data folder holding raw/ (default: the repo's data/)")
    ap.add_argument("--coarsen", type=int, default=1, help="average the getter's 200 m grid by this factor (default 1 = native)")
    ap.add_argument("--force", action="store_true", help="rebuild even if the saved graph is fresh")
    ap.add_argument("--neighbours", type=int, choices=(4, 8), default=8)
    args = ap.parse_args(argv)

    if args.fake:
        grid = fake_grid(24, 30) if args.small else default_grid()
        # A "bowl" keeps elevations plausible at the full-size grid (a 10 deg ramp would exceed 30 km there).
        inputs = GraphInputs(grid=grid, relief=fake_relief(grid, "bowl", height_m=3000.0),
                             weather=fake_weather(grid), poi=fake_poi(grid))
        models = stub_models()
        out = args.out or FAKE_GRAPH_PATH
    else:
        try:
            settings = Settings(data_dir=args.data_dir) if args.data_dir else Settings()
            inputs = graph_inputs_from_registry(build_registry(settings), settings, args.coarsen)
        except LayerDataError as ex:
            print(f"cannot build the graph: {ex}", file=sys.stderr)
            return 2
        models = default_models()
        out = args.out or DEFAULT_GRAPH_PATH
    t0 = time.time()
    data, built = ensure_graph(out, inputs, models, BuildConfig(neighbours=args.neighbours), force=args.force)
    verb = "built" if built else "up to date (loaded)"
    print(f"{verb}: {out}  nodes={data.grid.n_nodes:,} edges={data.n_edges:,} "
          f"formula={data.formula_version} in {time.time() - t0:.1f}s")
    return 0
