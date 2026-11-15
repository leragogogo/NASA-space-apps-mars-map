"""Build the static weather layer from the raw MDAD file.

  python scripts/weather/build.py [--config config/mars.yaml]   (from the repo root; also run by download_data.py)

The dust-storm risk thresholds come from the `weather.risk_bins` section of config/mars.yaml and are recorded
in both JSON outputs (`risk_bins`), so the API can tell when the files were computed with other thresholds.

Reads  data/raw/mdad/MDAD_original
Writes data/raw/weather/
  context_weather_frames.geojson   1 deg cells x 4 seasons around Valles Marineris (the app layer)
  aoi_weather_frames.json          the 4 AOI frames (summary card)
  observation_gaps.csv             imaging gaps used for the coverage rebuild
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ""):  # allow `python scripts/weather/build.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from weather import config as cfg  # noqa: E402
from weather.confidence import evaluate, grid_frames, message, observation_gaps, observed_years  # noqa: E402
from weather.mdad import hits_box, load_mdad  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SRC = ROOT / "data" / "raw" / "mdad" / "MDAD_original"
DEFAULT_OUT = ROOT / "data" / "raw" / "weather"


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def _feature(frame: dict, cell: float) -> dict:
    lon, lat, half = frame["lon"], frame["lat"], cell / 2
    ring = [[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
            [lon - half, lat + half], [lon - half, lat - half]]
    props = {k: v for k, v in frame.items() if k not in ("lon", "lat")}
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": props}


def build_weather_layer(src: Path = DEFAULT_SRC, out_dir: Path = DEFAULT_OUT, risk_bins: dict | None = None) -> dict:
    """Run the pipeline; returns a summary {files, frames, risk_bins, confidence counts per season}.

    `risk_bins` ({"moderate_from", "high_from"} in storm-days per Mars year) defaults to config/mars.yaml.
    """
    src, out_dir = Path(src), Path(out_dir)
    if not src.is_file():
        raise FileNotFoundError(f"{src} not found; run `python scripts/download_data.py --only mdad` first")
    bins = cfg.check_risk_bins(risk_bins if risk_bins is not None else cfg.risk_bins_from_config())
    previous = cfg.set_risk_bins(bins)
    try:
        return _build(src, out_dir, bins)
    finally:
        cfg.RISK_BINS = previous  # the thresholds are only in force while this build runs


def _build(src: Path, out_dir: Path, bins: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    d = load_mdad(src)
    gaps = observation_gaps(d)
    gaps.to_csv(out_dir / "observation_gaps.csv", index=False)

    aoi_lat = (cfg.AOI[1] + cfg.AOI[3]) / 2
    yrs = observed_years(gaps, aoi_lat)
    h = hits_box(d, cfg.AOI)
    aoi = []
    for name in cfg.SEASON_NAMES:
        f = evaluate(h[h.season == name], yrs[name])
        f["season"] = name
        f["message"] = message(f, name, "East Melas")
        aoi.append(f)
    (out_dir / "aoi_weather_frames.json").write_text(json.dumps(
        {"aoi": cfg.AOI, "caveat": cfg.GLOBAL_CAVEAT, "risk_bins": bins, "frames": aoi}, indent=1, default=_json_default))

    frames = grid_frames(d, gaps, cfg.CONTEXT, cfg.CELL)
    (out_dir / "context_weather_frames.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "caveat": cfg.GLOBAL_CAVEAT, "risk_bins": bins,
         "features": [_feature(f, cfg.CELL) for f in frames]}, default=_json_default))

    counts: dict[str, dict[str, int]] = {}
    for f in frames:
        c = counts.setdefault(f["season"], {})
        c[f["confidence"]] = c.get(f["confidence"], 0) + 1
    return {"files": sorted(p.name for p in out_dir.iterdir()), "frames": len(frames), "risk_bins": bins,
            "confidence_by_season": counts}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--config", type=Path, default=None, help="configuration file (default: $MARS_CONFIG, else config/mars.yaml)")
    args = ap.parse_args()
    print(json.dumps(build_weather_layer(args.src, args.out, cfg.risk_bins_from_config(args.config)), indent=1))


if __name__ == "__main__":
    main()
