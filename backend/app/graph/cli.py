"""Step 8: `python -m app.graph`: build (or reuse) graph.npz.

    python -m app.graph --fake            build from synthetic layers + stub profiles (dev/demo)
    python -m app.graph --fake --small    ... on a tiny grid (fast)
    python -m app.graph                   the ingested layers (data/raw/, app.layers.inputs.load_all) + the real profile models
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from app.graph.build import BuildConfig
from app.graph.fakes import stub_models
from app.graph.store import DEFAULT_GRAPH_PATH, ensure_graph
from app.core.configfile import ConfigError, load_settings
from app.layers.contracts import GraphInputs, LayerDataError, default_grid
from app.layers.fakes import fake_grid, fake_poi, fake_relief, fake_weather
from app.layers.inputs.load import load_all
from app.routing.profiles import models_from_settings

FAKE_GRAPH_PATH = DEFAULT_GRAPH_PATH.with_name("graph_fake.npz")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.graph", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fake", action="store_true", help="synthetic layers and stub profile models")
    ap.add_argument("--small", action="store_true", help="with --fake: use a tiny grid")
    ap.add_argument("--out", type=Path, default=None, help=f"default {DEFAULT_GRAPH_PATH} (fake: {FAKE_GRAPH_PATH})")
    ap.add_argument("--data-dir", type=Path, default=None, help="data folder holding raw/ (default: the repo's data/)")
    ap.add_argument("--config", type=Path, default=None,
                    help="configuration file (default: $MARS_CONFIG, else config/mars.yaml)")
    ap.add_argument("--coarsen", type=int, default=None,
                    help="average the 200 m DEM by this factor (default: Settings.grid_coarsen, 1 = native 200 m)")
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
        config = BuildConfig(neighbours=args.neighbours)
    else:
        overrides = {k: v for k, v in (("data_dir", args.data_dir), ("grid_coarsen", args.coarsen)) if v is not None}
        try:
            settings = load_settings(args.config, **overrides)
        except ConfigError as ex:
            print(f"invalid configuration: {ex}", file=sys.stderr)
            return 2
        try:
            inputs = load_all(settings)
        except LayerDataError as ex:
            print(f"cannot build the graph: {ex}", file=sys.stderr)
            return 2
        models = models_from_settings(settings)  # the parameters of the configuration file
        config = BuildConfig(neighbours=args.neighbours, rsl_buffer_m=settings.rsl_buffer_m)
        out = args.out or settings.graph_file  # the file the app loads at startup
    t0 = time.time()
    data, built = ensure_graph(out, inputs, models, config, force=args.force)
    verb = "built" if built else "up to date (loaded)"
    print(f"{verb}: {out}  nodes={data.grid.n_nodes:,} edges={data.n_edges:,} "
          f"formula={data.formula_version} in {time.time() - t0:.1f}s")
    return 0
