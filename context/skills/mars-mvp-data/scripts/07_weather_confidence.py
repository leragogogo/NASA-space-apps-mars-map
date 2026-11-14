"""Step 7: Weather layer with explicit data-sufficiency labels.

Every frame (one grid cell, or the AOI, in one season) gets:
  confidence = "reliable" | "approximate" | "insufficient_data"
  - reliable:          enough observed Mars years and storm events. The value is shown as-is.
  - approximate:       some data, but too little or too skewed. A best estimate is shown, clearly labelled.
  - insufficient_data: too few observed years in this frame. Risk is NOT calculated from the frame.
                       An approximate value is borrowed from neighbouring frames and labelled as such.

Why observation coverage matters: MDAD lists only storms, never "observed, no storm". So zero
storms is not the same as no risk. Coverage is rebuilt from the catalogue:
  * MY24 starts at Ls 150; MY32 ends at Ls 171.
  * MOC era (MY24-27) only mapped 60S-60N; MARCI era (MY28-32) is global.
  * Ls windows of >=10 deg with no storm anywhere on the planet are treated as imaging gaps.
    Example: MY29 Ls330 to MY30 Ls20, the MRO safe-mode period.

Outputs (outputs/weather/):
  observation_gaps.csv
  aoi_weather_frames.json          AOI x 4 seasons, app-ready
  context_weather_frames.geojson   1 deg cells x seasons around Valles Marineris, app-ready
  global_confidence_summary.csv    5 deg global run, showing where data is insufficient
"""
import json
import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
w6 = import_module("06_mdad_weather")
AOI, SEASONS, inside, hits_box = w6.AOI, w6.SEASONS, w6.inside, w6.hits_box
OUT = ROOT / "outputs" / "weather"

# ---------------- thresholds (tune here)
MIN_YEARS_RELIABLE = 6.0        # observed Mars years in the frame-season
MIN_YEARS_ANY = 3.0             # below this the frame itself cannot be used
MIN_STORMS_RELIABLE = 5         # distinct storms; fewer -> wide uncertainty
MAX_SINGLE_YEAR_SHARE = 0.5     # one Mars year contributing >50 % of storm-days -> skewed
MAX_MISSING_SHARE = 0.5         # >50 % of storm records flagged "missing data" in source images
NEIGHBOUR_RADIUS_DEG = 3.0
RISK_BINS = [(1.0, "Low"), (4.0, "Moderate"), (np.inf, "High")]  # storm-days per Mars year
SOLS_PER_SEASON = 668.6 / 4
GLOBAL_CAVEAT = ("Source: MDAD, MY24-32 (1999-2015). Dust storms smaller than ~100,000 km² are not reliably "
                 "catalogued, and storm footprints are ellipse approximations (no outlines in the source). "
                 "Values are historical frequencies, not forecasts.")


def risk_of(rate):
    for edge, name in RISK_BINS:
        if rate < edge:
            return name


# ---------------- observation coverage
def observation_gaps(d, min_gap_deg=10):
    gaps = []
    for my, g in d.groupby("my"):
        have = set((g.ls // 5).astype(int))
        lo = 30 if my == 24 else 0
        hi = 34 if my == 32 else 72
        run = []
        for k in list(range(lo, hi)) + [None]:
            if k is not None and k not in have:
                run.append(k)
                continue
            if len(run) * 5 >= min_gap_deg:
                gaps.append(dict(my=my, ls_from=run[0] * 5, ls_to=run[-1] * 5 + 5))
            run = []
    return pd.DataFrame(gaps)


def observed_years(gaps, lat):
    """Effective Mars years observed per season at a latitude."""
    out = {}
    for a, b, name in SEASONS:
        yrs = 0.0
        for my in range(24, 33):
            if abs(lat) > 60 and my < 28:  # MOC-era maps stop at 60 deg
                continue
            lo = max(a, 150) if my == 24 else a
            hi = min(b, 171) if my == 32 else b
            span = max(0.0, hi - lo)
            for _, gp in gaps[gaps.my == my].iterrows():
                span -= max(0.0, min(hi, gp.ls_to) - max(lo, gp.ls_from))
            yrs += max(0.0, span) / (b - a)
        out[name] = round(yrs, 2)
    return out


def poisson_ci(k, t):
    lo = 0.0 if k == 0 else chi2.ppf(0.025, 2 * k) / 2
    hi = chi2.ppf(0.975, 2 * k + 2) / 2
    return lo / t, hi / t


# ---------------- per-frame evaluation
def evaluate(h, years):
    """h: storm-sol rows hitting the frame in this season. Returns frame dict (without neighbour fill)."""
    n_days, n_storms = len(h), h.storm_id.nunique() if len(h) else 0
    f = dict(observed_years=years, storm_days=n_days, storms=n_storms, reasons=[])
    if years < MIN_YEARS_ANY:
        f.update(confidence="insufficient_data", rate=None, risk=None)
        f["reasons"].append(f"only {years:.1f} Mars years of imaging cover this frame and season "
                            f"(need ≥{MIN_YEARS_ANY:.0f})")
        return f
    rate = n_days / years
    s_lo, s_hi = poisson_ci(n_storms, years)
    days_per_storm = n_days / n_storms if n_storms else 1.0
    f.update(rate=round(rate, 2), rate_ci95=[round(s_lo * days_per_storm, 2), round(s_hi * days_per_storm, 2)],
             storms_per_year=round(n_storms / years, 2), risk=risk_of(rate))
    if years < MIN_YEARS_RELIABLE:
        f["reasons"].append(f"only {years:.1f} Mars years observed (need ≥{MIN_YEARS_RELIABLE:.0f})")
    if 0 < n_storms < MIN_STORMS_RELIABLE:
        f["reasons"].append(f"only {n_storms} storm(s) recorded; too few for a stable frequency")
    if n_days:
        by_year = h.groupby("my").size()
        share = by_year.max() / n_days
        if share > MAX_SINGLE_YEAR_SHARE and n_days >= 3:
            top = int(by_year.idxmax())
            typical = (n_days - by_year.max()) / max(years - 1, 1)
            f["reasons"].append(f"{by_year.max()} of {n_days} storm-days come from a single Mars year (MY{top})")
            f.update(typical_year_rate=round(typical, 2), typical_year_risk=risk_of(typical),
                     extreme_year=dict(my=top, storm_days=int(by_year.max()), risk=risk_of(by_year.max())))
        miss = (h.missing == "yes").mean()
        if miss > MAX_MISSING_SHARE:
            f["reasons"].append(f"{miss:.0%} of storm records come from images with missing data")
    f["confidence"] = "approximate" if f["reasons"] else "reliable"
    if f["confidence"] == "reliable" and n_storms == 0:
        f["reasons"].append(f"no storms in {years:.1f} observed Mars years; upper 95 % bound "
                            f"{s_hi:.2f} storms/yr")
    return f


def message(f, season, where):
    s = season.split(" (")[0]
    if f["confidence"] == "reliable":
        return (f"{f['risk']} dust-storm risk in {s}: ~{f['rate']} storm-days per Mars year "
                f"({f['storms']} storms over {f['observed_years']} observed Mars years).")
    if f["confidence"] == "approximate":
        main = f.get("typical_year_risk") or f["risk"]
        val = f.get("typical_year_rate", f["rate"])
        txt = (f"APPROXIMATE: not enough data to reliably calculate the risk for {where} in {s}. "
               f"Best estimate: {main} (~{val} storm-days per Mars year")
        txt += ", typical year)" if "typical_year_rate" in f else f"; 95 % range {f['rate_ci95'][0]}–{f['rate_ci95'][1]})"
        if "extreme_year" in f:
            e = f["extreme_year"]
            txt += f". Extreme year MY{e['my']}: {e['storm_days']} storm-days ({e['risk']})"
        return txt + ". Why: " + "; ".join(f["reasons"]) + "."
    est = f.get("neighbour_estimate")
    base = f"NOT ENOUGH DATA: dust-storm risk cannot be reliably calculated for {where} in {s} ({f['reasons'][0]})."
    if est:
        return base + (f" Approximate estimate from {est['n_frames']} neighbouring frames: {est['risk']} "
                       f"(~{est['rate']} storm-days per Mars year). Indicative only.")
    return base + " No approximate estimate is possible (no usable neighbouring frames)."


def grid_frames(d, gaps, box, cell):
    w, s, e, n = box
    sub = d[(d.lat_c - d.semi_lat_deg <= n) & (d.lat_c + d.semi_lat_deg >= s)]
    frames = []
    for lat in np.arange(s + cell / 2, n, cell):
        yrs = observed_years(gaps, lat)
        for lon in np.arange(w + cell / 2, e, cell):
            hit = sub[inside(sub, lon, lat)]
            for *_, sn in SEASONS:
                f = evaluate(hit[hit.season == sn], yrs[sn])
                frames.append(dict(lon=round(lon, 3), lat=round(lat, 3), season=sn, **f))
    df = pd.DataFrame(frames)
    # neighbour fill for insufficient frames
    usable = df[df.confidence != "insufficient_data"]
    for i in df.index[df.confidence == "insufficient_data"]:
        r = df.loc[i]
        nb = usable[(usable.season == r.season) & ((usable.lon - r.lon).abs() <= NEIGHBOUR_RADIUS_DEG)
                    & ((usable.lat - r.lat).abs() <= NEIGHBOUR_RADIUS_DEG)]
        if len(nb):
            m = float(nb.rate.mean())
            df.at[i, "neighbour_estimate"] = {"rate": round(m, 2), "risk": risk_of(m), "n_frames": len(nb)}
    if "neighbour_estimate" not in df:
        df["neighbour_estimate"] = None
    df = df.astype(object).where(df.notna(), None)  # NaN -> None so absent keys stay absent
    clean = [{k: v for k, v in r.items() if v is not None} for r in df.to_dict("records")]
    df["message"] = [message(r, r["season"], "this area") for r in clean]
    return df


def main():
    d = pd.read_csv(OUT / "mdad_clean.csv")
    gaps = observation_gaps(d)
    gaps.to_csv(OUT / "observation_gaps.csv", index=False)
    print("Imaging gaps (>=10 deg Ls with no storm anywhere):\n", gaps.to_string(index=False))

    # ---- AOI frames
    aoi_lat = (AOI[1] + AOI[3]) / 2
    yrs = observed_years(gaps, aoi_lat)
    h = hits_box(d, AOI)
    aoi = []
    for *_, sn in SEASONS:
        f = evaluate(h[h.season == sn], yrs[sn])
        f["season"] = sn
        f["message"] = message(f, sn, "East Melas")
        aoi.append(f)
    (OUT / "aoi_weather_frames.json").write_text(json.dumps(
        {"aoi": AOI, "caveat": GLOBAL_CAVEAT, "frames": aoi}, indent=1, default=float))
    print("\n=== AOI frames ===")
    for f in aoi:
        print(f"[{f['confidence'].upper()}] {f['message']}")

    # ---- context grid (for the app)
    ctx = grid_frames(d, gaps, w6.CONTEXT, 1.0)
    feats = [{"type": "Feature",
              "geometry": {"type": "Polygon", "coordinates": [[[r["lon"] - .5, r["lat"] - .5], [r["lon"] + .5, r["lat"] - .5],
                                                              [r["lon"] + .5, r["lat"] + .5], [r["lon"] - .5, r["lat"] + .5],
                                                              [r["lon"] - .5, r["lat"] - .5]]]},
              "properties": {k: v for k, v in r.items() if k not in ("lon", "lat")}}
             for r in ctx.to_dict("records")]
    (OUT / "context_weather_frames.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "caveat": GLOBAL_CAVEAT, "features": feats}, default=float))
    print("\n=== Context grid (1°, Valles Marineris) confidence counts ===")
    print(ctx.groupby(["season", "confidence"]).size().unstack(fill_value=0).to_string())

    # ---- global sanity run at 5 deg to see where data is insufficient
    glob = grid_frames(d, gaps, (-180, -90, 180, 90), 5.0)
    glob["lat_band"] = pd.cut(glob.lat, [-90, -60, -30, 0, 30, 60, 90])
    summ = glob.groupby(["lat_band", "confidence"], observed=True).size().unstack(fill_value=0)
    summ.to_csv(OUT / "global_confidence_summary.csv")
    print("\n=== Global 5° run: frames by latitude band x confidence ===\n", summ.to_string())
    ex = glob[glob.confidence == "insufficient_data"].head(1)
    if len(ex):
        print("\nExample insufficient frame:", ex.message.iloc[0])
    ex = glob[(glob.confidence == "approximate") & (glob.lat.abs() > 60)].head(1)
    if len(ex):
        print("Example polar approximate frame:", ex.message.iloc[0])


if __name__ == "__main__":
    main()
