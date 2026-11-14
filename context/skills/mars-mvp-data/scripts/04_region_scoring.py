"""Step 4: Score each candidate region by how much usable data each MVP layer has there.

- Layer 1 (base imagery): count + best resolution of servable imagery mosaics intersecting region
- Layer 2 (relief): best servable DEM / slope / hillshade products + % of region they cover
- Layer 3 (POI): number of vector features (from step 3) + mineral / dust rasters
"""
from pathlib import Path

import pandas as pd

from importlib import import_module
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
REGIONS = import_module("03_poi_features").REGIONS


def overlap_frac(r, bbox):
    w, s, e, n = bbox
    ix = max(0, min(e, r.east) - max(w, r.west))
    iy = max(0, min(n, r.north) - max(s, r.south))
    return ix * iy / ((e - w) * (n - s))


def main():
    cat = pd.read_csv(ROOT / "outputs" / "catalog_with_services.csv")
    cat = cat[(cat.proj == "eq")]
    local = cat[cat.area_deg2 < 1000]
    poi = pd.read_csv(ROOT / "outputs" / "poi_counts_long.csv")
    poi = poi[~poi.service.isin(["combinedNom", "major_features", "SIM3292_Global_Geology"])]

    rows, detail = [], []
    for reg, bbox in REGIONS.items():
        hits = local.assign(ov=local.apply(lambda r: overlap_frac(r, bbox), axis=1))
        hits = hits[hits.ov > 0]
        for _, h in hits.iterrows():
            detail.append(dict(region=reg, title=h.title, label=h.label, cat2=h.cat2, instrument=h.instrument,
                               wmts_ok=h.wmts_ok, m_per_px=h.best_m_per_px, region_cover_pct=round(100 * h.ov, 1)))
        ok = hits[hits.wmts_ok == True]  # noqa
        img = ok[ok.cat2.isin(["Mosaic", "Color Mosaic"])]
        rel = ok[ok.cat2.isin(["DEM", "Slope Colorized", "Slope", "Hillshade", "ColorHillshade"])]
        rel_all = hits[hits.cat2.isin(["DEM", "Slope"])]
        p = poi[poi.region == reg]
        rows.append(dict(
            region=reg,
            local_layers_total=len(hits), local_layers_servable=len(ok),
            imagery_layers=len(img), imagery_cover_pct=round(min(100, 100 * img.ov.sum()), 0),
            relief_layers=len(rel), relief_cover_pct=round(min(100, 100 * rel.ov.sum()), 0),
            raw_dem_slope_products=len(rel_all),
            hires_hirise=int((hits.instrument == "HiRISE").sum()),
            poi_features=int(p.n_features.sum()),
            poi_layer_types=int((p.groupby("layer").n_features.sum() > 0).sum()),
        ))
    s = pd.DataFrame(rows)
    # simple normalized score: each criterion scaled 0..1, equal weight
    crit = ["local_layers_servable", "imagery_cover_pct", "relief_layers", "relief_cover_pct", "poi_features", "poi_layer_types"]
    for c in crit:
        s[c + "_n"] = s[c] / s[c].max() if s[c].max() else 0
    s["score"] = s[[c + "_n" for c in crit]].mean(axis=1).round(3)
    s = s.drop(columns=[c + "_n" for c in crit]).sort_values("score", ascending=False)
    s.to_csv(ROOT / "outputs" / "region_scores.csv", index=False)
    pd.DataFrame(detail).to_csv(ROOT / "outputs" / "region_layer_detail.csv", index=False)
    pd.set_option("display.width", 250)
    print(s.to_string(index=False))


if __name__ == "__main__":
    main()
