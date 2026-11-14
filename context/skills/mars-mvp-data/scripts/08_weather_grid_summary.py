"""Step 8: Summarise and preview the weather layer.
The layer is the 1 deg Valles Marineris grid (CONTEXT in 06) produced by script 07.

Outputs (outputs/weather/):
  grid_risk_confidence_summary.csv   frames per season x risk x confidence
  weather_layer_preview.png          risk per season; approximate frames hatched, insufficient grey
"""
import json
import sys
from importlib import import_module
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch, Rectangle
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
w6 = import_module("06_mdad_weather")
OUT = ROOT / "outputs" / "weather"
RISK = {"Low": 0, "Moderate": 1, "High": 2}
COLORS = ["#2e7d32", "#f9a825", "#c62828"]


def main():
    gj = json.loads((OUT / "context_weather_frames.geojson").read_text())
    rows = []
    for f in gj["features"]:
        p = dict(f["properties"])
        ring = f["geometry"]["coordinates"][0]
        p["lon"] = (ring[0][0] + ring[1][0]) / 2
        p["lat"] = (ring[0][1] + ring[2][1]) / 2
        # The displayed risk: typical-year risk if skewed, neighbour estimate if insufficient, else risk
        est = p.get("neighbour_estimate") or {}
        p["display_risk"] = p.get("typical_year_risk") or p.get("risk") or est.get("risk")
        rows.append(p)
    df = pd.DataFrame(rows)
    summ = df.groupby(["season", "display_risk", "confidence"]).size().unstack(fill_value=0)
    summ.to_csv(OUT / "grid_risk_confidence_summary.csv")
    print(summ.to_string())

    w, s, e, n = w6.CONTEXT
    aoi = w6.AOI
    fig, axes = plt.subplots(2, 2, figsize=(14, 13))
    for ax, (*_, sn) in zip(axes.ravel(), w6.SEASONS):
        g = df[df.season == sn]
        grid = g.pivot(index="lat", columns="lon", values="display_risk").replace(RISK).astype(float)
        ax.imshow(grid.values, origin="lower", extent=[w, e, s, n], cmap=ListedColormap(COLORS), vmin=0, vmax=2)
        for r in g.itertuples():
            if r.confidence == "approximate":
                ax.add_patch(Rectangle((r.lon - .5, r.lat - .5), 1, 1, fill=False, hatch="///", lw=0, ec="white", alpha=.6))
            elif r.confidence == "insufficient_data":
                ax.add_patch(Rectangle((r.lon - .5, r.lat - .5), 1, 1, fc="grey", alpha=.7, lw=0))
        ax.add_patch(Rectangle((aoi[0], aoi[1]), aoi[2] - aoi[0], aoi[3] - aoi[1], fill=False, ec="cyan", lw=2.5))
        cnt = g.confidence.value_counts()
        ax.set_title(f"{sn}\nreliable {cnt.get('reliable', 0)} · approximate {cnt.get('approximate', 0)} · "
                     f"insufficient {cnt.get('insufficient_data', 0)}")
    handles = [Patch(color=c, label=l) for l, c in zip(RISK, COLORS)] + [
        Patch(fc="none", hatch="///", ec="k", label="approximate (labelled)"),
        Patch(fc="grey", label="not enough data (neighbour estimate)"),
        Patch(fc="none", ec="cyan", lw=2, label="demo AOI (East Melas)")]
    fig.legend(handles=handles, loc="lower center", ncol=6)
    fig.suptitle("Weather layer: seasonal dust-storm risk, Valles Marineris 1° grid (MDAD MY24-32)")
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    fig.savefig(OUT / "weather_layer_preview.png", dpi=90)


if __name__ == "__main__":
    main()
