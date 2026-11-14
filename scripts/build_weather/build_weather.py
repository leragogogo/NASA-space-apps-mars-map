#!/usr/bin/env python3
"""Build the Layer 4 weather files from the downloaded Mars Dust Activity Database (MDAD).

Input : data/raw/mdad/MDAD_original                         (fetched by scripts/download_data.py)
Output: data/derived/weather/context_weather_frames.geojson  1 deg cells x 4 seasons, Valles Marineris (served by the API)
        data/derived/weather/aoi_weather_frames.json         East Melas demo area x 4 seasons

Port of context/skills/mars-mvp-data/scripts/06_mdad_weather.py and 07_weather_confidence.py: same constants, rules
and messages. It is a copy because importing those scripts creates outputs/ and data/ folders inside the skill
directory. If the confidence rules change, change them in both places.

Usage (from repo root):
  pip install -r scripts/requirements.txt
  python scripts/build_weather/build_weather.py [--src PATH] [--out DIR]

Tests: pytest scripts/build_weather/tests
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[2]  # scripts/build_weather/build_weather.py -> repo root
DEFAULT_SRC = ROOT / "data" / "raw" / "mdad" / "MDAD_original"
DEFAULT_OUT = ROOT / "data" / "derived" / "weather"

AOI = (-71.8, -13.4, -68.0, -10.0)          # East Melas demo area (west, south, east, north)
CONTEXT = (-90.0, -30.0, -50.0, 10.0)       # Valles Marineris grid
R = 3389.5  # km, Mars mean radius
KM_PER_DEG = 2 * math.pi * R / 360

# Ls quarters. The AOI is at ~12 S, so seasons are named for the SOUTHERN hemisphere.
SEASONS = [(0, 90, "S. Autumn (Ls 0-90)"), (90, 180, "S. Winter (Ls 90-180)"),
           (180, 270, "S. Spring (Ls 180-270, perihelion)"), (270, 360, "S. Summer (Ls 270-360)")]

# ---------------- thresholds (keep in sync with skill script 07)
MIN_YEARS_RELIABLE = 6.0
MIN_YEARS_ANY = 3.0
MIN_STORMS_RELIABLE = 5
MAX_SINGLE_YEAR_SHARE = 0.5
MAX_MISSING_SHARE = 0.5
NEIGHBOUR_RADIUS_DEG = 3.0
RISK_BINS = [(1.0, "Low"), (4.0, "Moderate"), (np.inf, "High")]  # storm-days per Mars year
GLOBAL_CAVEAT = ("Source: MDAD, MY24-32 (1999-2015). Dust storms smaller than ~100,000 km² are not reliably "
                 "catalogued, and storm footprints are ellipse approximations (no outlines in the source). "
                 "Values are historical frequencies, not forecasts.")


# ---------------- from skill script 06
def season_of(ls):
    for a, b, n in SEASONS:
        if a <= ls < b:
            return n
    return SEASONS[-1][2]


def load(src):
    d = pd.read_csv(src)
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
    b_km = np.maximum((d.lat_max - d.lat_min) / 2 * KM_PER_DEG, 1.0)
    a_km = d.area_km2 / (math.pi * b_km)
    d["semi_lat_deg"] = b_km / KM_PER_DEG
    d["semi_lon_deg"] = a_km / (KM_PER_DEG * np.maximum(np.cos(np.radians(d.lat)), 0.05))
    d["lat_c"] = (d.lat_max + d.lat_min) / 2
    return d


def inside(d, lon, lat):
    dlon = (lon - d.lon + 180) % 360 - 180
    return (dlon / d.semi_lon_deg) ** 2 + ((lat - d.lat_c) / d.semi_lat_deg) ** 2 <= 1


def hits_box(d, box, step=0.25):
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


# ---------------- from skill script 07
def risk_of(rate):
    for edge, name in RISK_BINS:
        if rate < edge:
            return name


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
    out = {}
    for a, b, name in SEASONS:
        yrs = 0.0
        for my in range(24, 33):
            if abs(lat) > 60 and my < 28:
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


def evaluate(h, years):
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
    df = df.astype(object).where(df.notna(), None)
    clean = [{k: v for k, v in r.items() if v is not None} for r in df.to_dict("records")]
    df["message"] = [message(r, r["season"], "this area") for r in clean]
    return df


# ---------------- build
def build(src: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = load(src)
    gaps = observation_gaps(d)

    aoi_lat = (AOI[1] + AOI[3]) / 2
    yrs = observed_years(gaps, aoi_lat)
    h = hits_box(d, AOI)
    aoi = []
    for *_, sn in SEASONS:
        f = evaluate(h[h.season == sn], yrs[sn])
        f["season"] = sn
        f["message"] = message(f, sn, "East Melas")
        aoi.append(f)
    (out / "aoi_weather_frames.json").write_text(json.dumps(
        {"aoi": AOI, "caveat": GLOBAL_CAVEAT, "frames": aoi}, indent=1, default=float))

    ctx = grid_frames(d, gaps, CONTEXT, 1.0)
    feats = [{"type": "Feature",
              "geometry": {"type": "Polygon", "coordinates": [[[r["lon"] - .5, r["lat"] - .5], [r["lon"] + .5, r["lat"] - .5],
                                                              [r["lon"] + .5, r["lat"] + .5], [r["lon"] - .5, r["lat"] + .5],
                                                              [r["lon"] - .5, r["lat"] - .5]]]},
              "properties": {k: v for k, v in r.items() if k not in ("lon", "lat")}}
             for r in ctx.to_dict("records")]
    (out / "context_weather_frames.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "caveat": GLOBAL_CAVEAT, "features": feats}, default=float))
    return {"cells": len(feats), "aoi_frames": len(aoi)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="MDAD CSV (default: data/raw/mdad/MDAD_original)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output folder (default: data/derived/weather)")
    args = ap.parse_args()
    if not args.src.is_file():
        raise SystemExit(f"{args.src} not found. Run: python scripts/download_data.py --only mdad")
    info = build(args.src, args.out)
    print(f"wrote {info['cells']} weather cells and {info['aoi_frames']} demo-area frames to {args.out}")


if __name__ == "__main__":
    main()
