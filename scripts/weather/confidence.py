"""Weather frames with explicit data-sufficiency labels (SKILL.md section 6).

Every frame (one grid cell, or the AOI, in one season) gets:
  confidence = "reliable" | "approximate" | "insufficient_data"
  - reliable:          enough observed Mars years and storm events; the value is shown as-is.
  - approximate:       some data, but too little or too skewed; a best estimate, clearly labelled.
  - insufficient_data: too few observed years; risk is NOT calculated from the frame, an
                       approximate value is borrowed from neighbouring frames and labelled so.

MDAD lists only storms, never "observed, no storm", so zero storms is not the same as no risk.
Coverage is rebuilt from the catalogue (MY24 starts at Ls150, MY32 ends at Ls171, MOC-era maps stop
at 60 deg, and Ls windows of >=10 deg with no storm anywhere are treated as imaging gaps).

A frame is a plain dict; optional keys (typical_year_*, extreme_year, neighbour_estimate) are absent,
not null, when they do not apply.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2

from weather import config as cfg
from weather.mdad import inside


def risk_of(rate: float) -> str:
    for edge, name in cfg.RISK_BINS:
        if rate < edge:
            return name
    return cfg.RISK_BINS[-1][1]


def observation_gaps(d: pd.DataFrame, min_gap_deg: int = 10) -> pd.DataFrame:
    """Ls windows (per Mars year) of >= min_gap_deg with no storm anywhere on the planet."""
    gaps = []
    for my, g in d.groupby("my"):
        have = set((g.ls // 5).astype(int))
        lo = 30 if my == cfg.FIRST_MY else 0
        hi = 34 if my == cfg.LAST_MY else 72
        run: list[int] = []
        for k in list(range(lo, hi)) + [None]:
            if k is not None and k not in have:
                run.append(k)
                continue
            if len(run) * 5 >= min_gap_deg:
                gaps.append(dict(my=int(my), ls_from=run[0] * 5, ls_to=run[-1] * 5 + 5))
            run = []
    return pd.DataFrame(gaps, columns=["my", "ls_from", "ls_to"])


def observed_years(gaps: pd.DataFrame, lat: float) -> dict[str, float]:
    """Effective Mars years observed per season at a latitude."""
    out = {}
    for a, b, name in cfg.SEASONS:
        yrs = 0.0
        for my in range(cfg.FIRST_MY, cfg.LAST_MY + 1):
            if abs(lat) > 60 and my < 28:  # MOC-era maps stop at 60 deg
                continue
            lo = max(a, cfg.FIRST_LS) if my == cfg.FIRST_MY else a
            hi = min(b, cfg.LAST_LS) if my == cfg.LAST_MY else b
            span = max(0.0, hi - lo)
            for _, gp in gaps[gaps.my == my].iterrows():
                span -= max(0.0, min(hi, gp.ls_to) - max(lo, gp.ls_from))
            yrs += max(0.0, span) / (b - a)
        out[name] = round(yrs, 2)
    return out


def poisson_ci(k: int, t: float) -> tuple[float, float]:
    lo = 0.0 if k == 0 else chi2.ppf(0.025, 2 * k) / 2
    hi = chi2.ppf(0.975, 2 * k + 2) / 2
    return lo / t, hi / t


def evaluate(h: pd.DataFrame, years: float) -> dict:
    """h: storm-sol rows hitting the frame in this season. Returns the frame dict (no neighbour fill)."""
    n_days = len(h)
    n_storms = int(h.storm_id.nunique()) if n_days else 0
    f: dict = dict(observed_years=years, storm_days=n_days, storms=n_storms, reasons=[])
    if years < cfg.MIN_YEARS_ANY:
        f.update(confidence="insufficient_data")
        f["reasons"].append(f"only {years:.1f} Mars years of imaging cover this frame and season "
                            f"(need ≥{cfg.MIN_YEARS_ANY:.0f})")
        return f
    rate = n_days / years
    s_lo, s_hi = poisson_ci(n_storms, years)
    days_per_storm = n_days / n_storms if n_storms else 1.0
    f.update(rate=round(rate, 2), rate_ci95=[round(s_lo * days_per_storm, 2), round(s_hi * days_per_storm, 2)],
             storms_per_year=round(n_storms / years, 2), risk=risk_of(rate))
    if years < cfg.MIN_YEARS_RELIABLE:
        f["reasons"].append(f"only {years:.1f} Mars years observed (need ≥{cfg.MIN_YEARS_RELIABLE:.0f})")
    if 0 < n_storms < cfg.MIN_STORMS_RELIABLE:
        f["reasons"].append(f"only {n_storms} storm(s) recorded; too few for a stable frequency")
    if n_days:
        by_year = h.groupby("my").size()
        share = by_year.max() / n_days
        if share > cfg.MAX_SINGLE_YEAR_SHARE and n_days >= 3:
            top = int(by_year.idxmax())
            typical = (n_days - by_year.max()) / max(years - 1, 1)
            f["reasons"].append(f"{by_year.max()} of {n_days} storm-days come from a single Mars year (MY{top})")
            f.update(typical_year_rate=round(float(typical), 2), typical_year_risk=risk_of(typical),
                     extreme_year=dict(my=top, storm_days=int(by_year.max()), risk=risk_of(by_year.max())))
        miss = (h.missing == "yes").mean()
        if miss > cfg.MAX_MISSING_SHARE:
            f["reasons"].append(f"{miss:.0%} of storm records come from images with missing data")
    f["confidence"] = "approximate" if f["reasons"] else "reliable"
    if f["confidence"] == "reliable" and n_storms == 0:
        f["reasons"].append(f"no storms in {years:.1f} observed Mars years; upper 95 % bound {s_hi:.2f} storms/yr")
    return f


def message(f: dict, season: str, where: str) -> str:
    """The text the UI must show verbatim for a frame."""
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


def grid_frames(d: pd.DataFrame, gaps: pd.DataFrame, box, cell: float) -> list[dict]:
    """One frame per (cell, season) over box = (west, south, east, north); cell centres at
    lon/lat, with the neighbour estimate filled in for `insufficient_data` frames and `message` set."""
    w, s, e, n = box
    sub = d[(d.lat_c - d.semi_lat_deg <= n) & (d.lat_c + d.semi_lat_deg >= s)]
    frames: list[dict] = []
    for lat in np.arange(s + cell / 2, n, cell):
        yrs = observed_years(gaps, lat)
        for lon in np.arange(w + cell / 2, e, cell):
            hit = sub[inside(sub, lon, lat)]
            for name in cfg.SEASON_NAMES:
                f = evaluate(hit[hit.season == name], yrs[name])
                frames.append(dict(lon=round(float(lon), 3), lat=round(float(lat), 3), season=name, **f))
    usable = [f for f in frames if f["confidence"] != "insufficient_data"]
    for f in frames:
        if f["confidence"] != "insufficient_data":
            continue
        nb = [u for u in usable if u["season"] == f["season"]
              and abs(u["lon"] - f["lon"]) <= cfg.NEIGHBOUR_RADIUS_DEG
              and abs(u["lat"] - f["lat"]) <= cfg.NEIGHBOUR_RADIUS_DEG]
        if nb:
            m = float(np.mean([u["rate"] for u in nb]))
            f["neighbour_estimate"] = {"rate": round(m, 2), "risk": risk_of(m), "n_frames": len(nb)}
    for f in frames:
        f["message"] = message(f, f["season"], "this area")
    return frames
