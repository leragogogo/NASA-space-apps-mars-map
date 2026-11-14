"""Step 6: Weather layer exploration with the Mars Dust Activity Database (MDAD, Battalio & Wang 2021).

Source: Harvard Dataverse doi:10.7910/DVN/F8R2JX (file id 3607412), MY24 Ls150 -> MY32 Ls171.
Each row = one dust storm on one sol: centroid, area, min/max latitude. No outlines.

Storm footprint approximation: an ellipse centred on the centroid. Its N-S semi-axis comes from
the min/max latitude. Its E-W semi-axis is solved so the ellipse area equals the reported area.
A cell is "hit" on a sol if its centre lies inside the ellipse.

Outputs (outputs/weather/):
- mdad_clean.csv
- storm_hits_aoi.csv: every storm-sol touching the AOI
- seasonal_risk_aoi.csv: storm-sols and distinct storms per Mars season, normalised per Mars year
- context_grid_seasonal.csv: 1 deg grid around Valles Marineris, storm-sol frequency per season
- weather_preview.png
"""
import math
import sys
from importlib import import_module
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
AOI = import_module("05_aoi_deep_dive").AOI  # (-71.8, -13.4, -68.0, -10.0)
SRC = ROOT / "data" / "raw" / "mdad" / "MDAD_original"
OUT = ROOT / "outputs" / "weather"
OUT.mkdir(parents=True, exist_ok=True)

R = 3389.5  # km, Mars mean radius
KM_PER_DEG = 2 * math.pi * R / 360
CONTEXT = (-90.0, -30.0, -50.0, 10.0)  # Valles Marineris neighbourhood for relative risk
CELL = 1.0

# Ls quarters. The AOI is at ~12 S, so seasons are named for the SOUTHERN hemisphere.
SEASONS = [(0, 90, "S. Autumn (Ls 0-90)"), (90, 180, "S. Winter (Ls 90-180)"),
           (180, 270, "S. Spring (Ls 180-270, perihelion)"), (270, 360, "S. Summer (Ls 270-360)")]
# Observation window: MY24 Ls150 -> MY32 Ls171. Count how many Mars years observed each Ls quarter.
FIRST, LAST = (24, 150.0), (32, 171.0)


def season_of(ls):
    for a, b, n in SEASONS:
        if a <= ls < b:
            return n
    return SEASONS[-1][2]


def years_observed():
    out = {}
    for a, b, n in SEASONS:
        yrs = 0.0
        for my in range(FIRST[0], LAST[0] + 1):
            lo = max(a, FIRST[1]) if my == FIRST[0] else a
            hi = min(b, LAST[1]) if my == LAST[0] else b
            yrs += max(0.0, hi - lo) / (b - a)
        out[n] = round(yrs, 2)
    return out


def load():
    d = pd.read_csv(SRC)
    d.columns = [c.strip() for c in d.columns]
    for c in d.columns:
        if d[c].dtype == object or str(d[c].dtype) == "str":
            d[c] = d[c].astype(str).str.strip()
    d = d.rename(columns={"Mars Year": "my", "Mission subphase": "subphase", "Sol": "sol", "Ls": "ls",
                          "Centroid longitude": "lon", "Centroid latitude": "lat", "Area (square km)": "area_km2",
                          "Member ID": "member", "Sequence ID": "sequence", "Maximum latitude": "lat_max",
                          "Minimum latitude": "lat_min", "Confidence interval": "conf", "Missing data": "missing"})
    d["storm_id"] = d.subphase + "_" + d.member  # member ids restart per subphase
    d["season"] = d.ls.apply(season_of)
    # ellipse semi-axes in degrees
    b_km = np.maximum((d.lat_max - d.lat_min) / 2 * KM_PER_DEG, 1.0)
    a_km = d.area_km2 / (math.pi * b_km)
    d["semi_lat_deg"] = b_km / KM_PER_DEG
    d["semi_lon_deg"] = a_km / (KM_PER_DEG * np.maximum(np.cos(np.radians(d.lat)), 0.05))
    d["lat_c"] = (d.lat_max + d.lat_min) / 2  # use the latitude-span centre for the ellipse
    d.to_csv(OUT / "mdad_clean.csv", index=False)
    return d


def inside(d, lon, lat):
    dlon = (lon - d.lon + 180) % 360 - 180
    return (dlon / d.semi_lon_deg) ** 2 + ((lat - d.lat_c) / d.semi_lat_deg) ** 2 <= 1


def hits_box(d, box, step=0.25):
    """Storm-sols whose ellipse covers any sample point inside box."""
    w, s, e, n = box
    pts = [(x, y) for x in np.arange(w, e + 1e-9, step) for y in np.arange(s, n + 1e-9, step)]
    mask = np.zeros(len(d), bool)
    frac = np.zeros(len(d))
    for x, y in pts:
        m = inside(d, x, y).to_numpy()
        mask |= m
        frac += m
    out = d[mask].copy()
    out["aoi_cover_frac"] = (frac[mask] / len(pts)).round(2)
    return out


def main():
    d = load()
    yrs = years_observed()
    print(f"MDAD rows: {len(d)}, distinct storms: {d.storm_id.nunique()}, MY {d.my.min()}-{d.my.max()}")
    print("Mars years observed per season:", yrs)

    # ---------- AOI
    h = hits_box(d, AOI)
    h.to_csv(OUT / "storm_hits_aoi.csv", index=False)
    print(f"\nStorm-sols touching AOI: {len(h)} | distinct storms: {h.storm_id.nunique()}")
    g = h.groupby("season").agg(storm_sols=("sol", "size"), storms=("storm_id", "nunique"),
                                mean_area_km2=("area_km2", "mean"), max_area_km2=("area_km2", "max"),
                                mean_cover=("aoi_cover_frac", "mean"))
    g = g.reindex([n for *_, n in SEASONS]).fillna(0)
    g["years_observed"] = [yrs[n] for n in g.index]
    g["storm_sols_per_year"] = (g.storm_sols / g.years_observed).round(1)
    g["storms_per_year"] = (g.storms / g.years_observed).round(2)
    # ~167 sols per Ls quarter on average (668.6 sols/yr / 4)
    g["pct_of_sols_with_storm"] = (100 * g.storm_sols_per_year / (668.6 / 4)).round(1)
    g.to_csv(OUT / "seasonal_risk_aoi.csv")
    pd.set_option("display.width", 220)
    print(g.round(2).to_string())

    by_year = h.pivot_table(index="my", columns="season", values="sol", aggfunc="size", fill_value=0)
    by_year.to_csv(OUT / "aoi_storm_sols_by_year.csv")
    print("\nStorm-sols per Mars year x season:\n", by_year.to_string())

    # ---------- context grid
    w, s, e, n = CONTEXT
    lons = np.arange(w + CELL / 2, e, CELL)
    lats = np.arange(s + CELL / 2, n, CELL)
    sub = d[(d.lat_c - d.semi_lat_deg <= n) & (d.lat_c + d.semi_lat_deg >= s)]
    rows = []
    for x in lons:
        for y in lats:
            m = inside(sub, x, y)
            cnt = sub[m].groupby("season").size()
            for *_, sn in SEASONS:
                rows.append(dict(lon=x, lat=y, season=sn, storm_sols=int(cnt.get(sn, 0)),
                                 per_year=cnt.get(sn, 0) / yrs[sn]))
    grid = pd.DataFrame(rows)
    grid.to_csv(OUT / "context_grid_seasonal.csv", index=False)
    in_aoi = grid[(grid.lon.between(AOI[0], AOI[2])) & (grid.lat.between(AOI[1], AOI[3]))]
    pct = {sn: round(100 * (grid[grid.season == sn].per_year < in_aoi[in_aoi.season == sn].per_year.mean()).mean())
           for *_, sn in SEASONS}
    print("\nAOI percentile vs Valles Marineris context grid (100 = stormiest):", pct)

    # ---------- figure
    fig, ax = plt.subplots(2, 3, figsize=(18, 10))
    vmax = grid.per_year.max()
    for i, (*_, sn) in enumerate(SEASONS):
        a = ax.ravel()[i]
        G = grid[grid.season == sn].pivot(index="lat", columns="lon", values="per_year")
        im = a.imshow(G.values, origin="lower", extent=[w, e, s, n], cmap="Reds", vmin=0, vmax=vmax)
        a.add_patch(plt.Rectangle((AOI[0], AOI[1]), AOI[2] - AOI[0], AOI[3] - AOI[1], fill=False, ec="cyan", lw=2))
        a.set_title(f"{sn}\nstorm-sols / Mars year per 1° cell")
        fig.colorbar(im, ax=a, shrink=0.8)
    a = ax.ravel()[4]
    a.bar(range(4), g.storm_sols_per_year, color="firebrick")
    a.set_xticks(range(4)); a.set_xticklabels([x.split(" (")[0] for x in g.index])
    a.set_title("AOI: storm-sols per Mars year, by season")
    a = ax.ravel()[5]
    a.hist(h.ls, bins=36, range=(0, 360), color="gray")
    a.set_title("AOI: storm-sols by Ls (all years)"); a.set_xlabel("Ls (deg)")
    fig.suptitle("MDAD dust storm frequency: East Melas AOI (cyan) in the Valles Marineris context")
    fig.tight_layout(); fig.savefig(OUT / "weather_preview.png", dpi=100)


if __name__ == "__main__":
    main()
