"""Step 5: Deep dive on the chosen demo AOI (East Melas Chasma core).

- Downloads real elevation values (int16 metres) from the Trek ArcGIS ImageServer (MOLA+HRSC blend, 200 m)
- Computes elevation range and slope classes (walkable / rover / impassable)
- Stitches WMTS tiles for the candidate visual layers to verify they render and measure tile coverage
- Overlays POI vectors and writes preview PNGs to outputs/aoi/
"""
import io
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import tifffile
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "aoi"
OUT.mkdir(parents=True, exist_ok=True)
CACHE = ROOT / "data" / "raw" / "tiles"
CACHE.mkdir(parents=True, exist_ok=True)
ARC = "https://trek.nasa.gov/mars/trekarcgis/rest/services"
NS = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}
M_PER_DEG = 2 * math.pi * 3396190 / 360  # Mars sphere

# Core demo AOI: densest overlap of CTX DEM/slope/hillshade tiles + RSLs + sulfates + Melas EZ
AOI = (-71.8, -13.4, -68.0, -10.0)  # west, south, east, north

LAYERS = {  # name -> (label, zoom)
    "base_ctx_global": ("CTX_beta01_uncontrolled_5m_Caltech", 9),
    "base_coprates_mosaic": ("Coprates_EMelas_Chasm_Mosaic", 9),
    "base_hirise_global": ("HiRISE_Global", 9),
    "relief_ctx_eastmelas_dem": ("East_Melas_DEM", 9),
    "relief_ctx_eastmelas_hillshade": ("East_Melas_Hillshade", 9),
    "relief_color_hillshade_blend": ("Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw", 8),
    "relief_color_slope_12S290E": ("CTX_ColorSlope_12S290E_24mp_D18_034250_1676_D21_035450_1674", 9),
    "poi_crism_polysulfate": ("MC18_PolySulfate_Mineral_IndicatorV2_SP", 9),
    "context_thermal_night": ("THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018", 8),
}


def resolve_labels():
    """Look up real productLabels from the catalog for the friendly names above."""
    cat = pd.read_csv(ROOT / "outputs" / "catalog_with_services.csv")
    cat = cat[(cat.proj == "eq") & (cat.wmts_ok == True)]  # noqa
    out = {}
    for k, (lab, z) in LAYERS.items():
        if lab in set(cat.label):
            out[k] = (lab, z)
            continue
        key = {"Coprates_EMelas_Chasm_Mosaic": "Coprates EMelas Chasm Mosaic", "East_Melas_DEM": "MRO CTX, East Melas DEM",
               "East_Melas_Hillshade": "MRO CTX, East Melas Hillshade",
               "CTX_ColorSlope_12S290E_24mp_D18_034250_1676_D21_035450_1674": "Color Slope East Melas 12S290E"}[lab]
        hit = cat[cat.title.str.contains(key, regex=False)]
        out[k] = (hit.label.iloc[0], z)
    return out


def caps(label):
    url = f"https://trek.nasa.gov/tiles/Mars/EQ/{label}/1.0.0/WMTSCapabilities.xml"
    root = ET.fromstring(requests.get(url, timeout=60).content)
    tmpl = root.find(".//w:ResourceURL", NS).get("template")
    style = root.find(".//w:Style/ows:Identifier", NS)
    tms = root.find(".//w:TileMatrixSetLink/w:TileMatrixSet", NS)
    tmpl = tmpl.replace("{Style}", style.text if style is not None else "default")
    tmpl = tmpl.replace("{TileMatrixSet}", tms.text if tms is not None else "default028mm")
    mats = root.findall(".//w:Contents/w:TileMatrixSet/w:TileMatrix", NS)
    info = {}
    for m in mats:
        z = int(m.find("ows:Identifier", NS).text)
        tw = int(m.find("w:TileWidth", NS).text)
        mw = float(m.find("w:MatrixWidth", NS).text)
        info[z] = (tw, 360.0 / mw)  # tile px, tile size in degrees
    return tmpl, info


def stitch(label, z, bbox):
    tmpl, info = caps(label)
    maxz = max(info)
    z = min(z, maxz)
    T, deg = info[z]
    w, s, e, n = bbox
    c0, c1 = int((w + 180) // deg), int((e + 180) // deg)
    r0, r1 = int((90 - n) // deg), int((90 - s) // deg)
    canvas = Image.new("RGBA", ((c1 - c0 + 1) * T, (r1 - r0 + 1) * T))
    got = tot = 0
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            tot += 1
            fn = CACHE / f"{label}_{z}_{r}_{c}.png"
            if not fn.exists():
                url = tmpl.replace("{TileMatrix}", str(z)).replace("{TileRow}", str(r)).replace("{TileCol}", str(c))
                resp = requests.get(url, timeout=60)
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                    fn.write_bytes(resp.content)
            if fn.exists():
                try:
                    canvas.paste(Image.open(fn).convert("RGBA").resize((T, T)), ((c - c0) * T, (r - r0) * T))
                    got += 1
                except Exception:
                    pass
    # crop to bbox
    px = deg / T
    x0 = int((w + 180 - c0 * deg) / px); x1 = int((e + 180 - c0 * deg) / px)
    y0 = int((90 - n - r0 * deg) / px); y1 = int((90 - s - r0 * deg) / px)
    img = np.array(canvas.crop((x0, y0, x1, y1)))
    alpha = img[..., 3] > 0
    nonblank = alpha & (img[..., :3].max(axis=-1) > 0)
    return img, dict(label=label, zoom=z, max_zoom=maxz, m_per_px_at_zoom=round(px * M_PER_DEG, 1),
                     m_per_px_max=round(info[maxz][1] / info[maxz][0] * M_PER_DEG, 1), tile_px=T,
                     tiles_ok=f"{got}/{tot}", aoi_pixel_coverage_pct=round(100 * nonblank.mean(), 1))


def dem_grid(service, bbox, size=1200):
    params = {"bbox": ",".join(map(str, bbox)), "bboxSR": 104905, "imageSR": 104905,
              "size": f"{size},{int(size * (bbox[3] - bbox[1]) / (bbox[2] - bbox[0]))}",
              "format": "tiff", "pixelType": "F32", "noData": -32767, "interpolation": "RSP_BilinearInterpolation",
              "f": "image"}
    r = requests.get(f"{ARC}/{service}/ImageServer/exportImage", params=params, timeout=300)
    r.raise_for_status()
    arr = tifffile.imread(io.BytesIO(r.content)).astype("float32")
    arr[arr <= -32000] = np.nan
    return arr


def slope_deg(dem, bbox):
    h, w = dem.shape
    dx = (bbox[2] - bbox[0]) / w * M_PER_DEG * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    dy = (bbox[3] - bbox[1]) / h * M_PER_DEG
    gy, gx = np.gradient(dem, dy, dx)
    return np.degrees(np.arctan(np.hypot(gx, gy))), dx, dy


def load_pois(bbox):
    feats = []
    for f in (ROOT / "data" / "raw" / "features").glob("*East*.geojson"):
        svc = f.name.split("__")[0]
        for ft in json.loads(f.read_text())["features"]:
            g = ft.get("geometry") or {}
            if g.get("type") == "Point":
                x, y = g["coordinates"][:2]
                if x > 180: x -= 360
                if bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]:
                    p = ft["properties"]
                    tag = p.get("Class") or p.get("Short_Type") or p.get("name") or svc.split("_")[0]
                    feats.append(dict(service=svc, kind=tag, lon=x, lat=y))
    return pd.DataFrame(feats).drop_duplicates()


def main():
    ext = [AOI[0], AOI[2], AOI[1], AOI[3]]
    # ---- Relief: real numbers
    dem = dem_grid("Mars_MOLA_blend200ppx_HRSC_DEM_clon0dd_200mpp_lzw", AOI)
    np.save(OUT / "dem_blend200m_aoi.npy", dem)
    slp, dx, dy = slope_deg(dem, AOI)
    bins = [0, 5, 15, 25, 35, 90]
    names = ["0-5° easy walk", "5-15° walkable", "15-25° rover only", "25-35° hard/rover limit", ">35° impassable"]
    cls = pd.cut(pd.Series(slp[np.isfinite(slp)].ravel()), bins, labels=names, include_lowest=True).value_counts(normalize=True)
    stats = {
        "aoi_bbox": AOI, "aoi_km": [round((AOI[2] - AOI[0]) * dx / ((AOI[2] - AOI[0]) / dem.shape[1]) / 1000, 1),
                                    round((AOI[3] - AOI[1]) * M_PER_DEG / 1000, 1)],
        "dem_grid_px": list(dem.shape), "dem_px_m": [round(dx), round(dy)],
        "elev_min_m": float(np.nanmin(dem)), "elev_max_m": float(np.nanmax(dem)),
        "relief_m": float(np.nanmax(dem) - np.nanmin(dem)),
        "slope_classes_pct (at ~200 m DEM, underestimates local slopes)": {k: round(100 * v, 1) for k, v in cls.items()},
    }
    # Sanity check elevation against hi-res CTX tiles is visual only (CTX DEM rasters are not served as values)
    print(json.dumps(stats, indent=1))

    # ---- Visual layers: verify they render
    labels = resolve_labels()
    reports, imgs = [], {}
    for k, (lab, z) in labels.items():
        try:
            img, rep = stitch(lab, z, AOI)
            imgs[k] = img
            reports.append({"layer": k, **rep})
            Image.fromarray(img).save(OUT / f"{k}.png")
        except Exception as e:
            reports.append({"layer": k, "label": lab, "error": str(e)[:120]})
        print(reports[-1])
    pd.DataFrame(reports).to_csv(OUT / "layer_render_report.csv", index=False)

    # ---- POIs
    pois = load_pois(AOI)
    pois.to_csv(OUT / "pois_in_aoi.csv", index=False)
    print(pois.groupby(["service", "kind"]).size())

    # ---- Preview figure
    fig, ax = plt.subplots(2, 3, figsize=(18, 11))
    a = ax[0, 0]; a.imshow(imgs.get("base_ctx_global"), extent=ext); a.set_title("L1 base: CTX global mosaic")
    a = ax[0, 1]; im = a.imshow(dem, extent=ext, cmap="terrain"); a.set_title("L2 relief: elevation (m), MOLA+HRSC 200 m")
    fig.colorbar(im, ax=a, shrink=0.8)
    a = ax[0, 2]; im = a.imshow(np.digitize(slp, bins[1:-1]), extent=ext, cmap=plt.get_cmap("RdYlGn_r", 5))
    a.set_title("L2 relief: slope class from DEM"); cb = fig.colorbar(im, ax=a, shrink=0.8, ticks=range(5)); cb.ax.set_yticklabels(names)
    a = ax[1, 0]; a.imshow(imgs.get("relief_ctx_eastmelas_hillshade"), extent=ext); a.set_title("L2 relief: CTX East Melas hillshade (tiles)")
    a = ax[1, 1]; a.imshow(imgs.get("relief_color_slope_12S290E"), extent=ext); a.set_title("L2 relief: CTX color slope 12S290E (tiles)")
    a = ax[1, 2]; a.imshow(imgs.get("base_ctx_global"), extent=ext, alpha=0.6); a.set_title("L3 POIs on CTX")
    if len(pois):
        for kind, g in pois.groupby("kind"):
            a.scatter(g.lon, g.lat, s=60, label=f"{kind} ({len(g)})", edgecolor="k")
        a.legend(fontsize=7, loc="lower left")
    for a in ax.ravel():
        a.set_xlim(AOI[0], AOI[2]); a.set_ylim(AOI[1], AOI[3])
    fig.suptitle(f"Demo AOI: East Melas Chasma  {AOI}")
    fig.tight_layout(); fig.savefig(OUT / "aoi_preview.png", dpi=110)
    (OUT / "relief_stats.json").write_text(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
