#!/usr/bin/env python3
"""Download every dataset the Mars MVP map uses, so nothing has to be fetched by hand.

Layout written under <repo>/data/raw/ (gitignored; same paths the skill scripts 05-07 expect):

  dem/dem_blend200m_aoi.tif          Layer 2  MOLA+HRSC 200 m DEM, float32 metres, AOI only
  tiles/<label>/<z>/<row>/<col>.ext  Layers 1-3  WMTS tiles over the AOI (row/col are WMTS, top-left origin)
  features/<service>__<id>.geojson   Layer 3  POI vectors intersecting the AOI
  mdad/MDAD_original                 Layer 4  Mars Dust Activity Database CSV (input for skill scripts 06-07)
  manifest.json                      what was fetched, when, and counts

Usage (from repo root):
  pip install -r scripts/requirements.txt
  python scripts/download_data.py                  # everything
  python scripts/download_data.py --only dem mdad  # a subset: dem | tiles | pois | mdad
  python scripts/download_data.py --max-zoom 8     # fewer tiles
  python scripts/download_data.py --force          # re-download existing files

Re-running is safe: existing files are skipped unless --force is given.
Details on why each dataset was chosen: context/skills/mars-mvp-data/SKILL.md
"""
import argparse
import concurrent.futures as cf
import io
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
import tifffile
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

# Demo AOI: East Melas / Coprates Chasma (west, south, east, north), lon -180..180
AOI = (-71.8, -13.4, -68.0, -10.0)

ARC = "https://trek.nasa.gov/mars/trekarcgis/rest/services"
WMTS = "https://trek.nasa.gov/tiles/Mars/EQ/{label}/1.0.0/WMTSCapabilities.xml"
MDAD_URL = "https://dataverse.harvard.edu/api/access/datafile/3607412?format=original"
NS = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}

DEM_SERVICE = "Mars_MOLA_blend200ppx_HRSC_DEM_clon0dd_200mpp_lzw"
DEM_WIDTH_PX = 1200

# role -> WMTS label. Roles/notes come from the skill (section 5).
TILE_LAYERS = {
    "L1 base (primary)": "Coprates_EMelas_Chasm_CTX_BlockAdj_dd",
    "L1 base (fallback)": "CTX_beta01_uncontrolled_5m_Caltech",
    "L1 zoom-in detail": "HiRISE_Global",
    "L2 colour hillshade (full coverage)": "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
    "L2 CTX hillshade (hi-res strips)": "CTX_Shade_East_Melas",
    "L3 CRISM polysulfate indicator": "MC18_PolySulfate_Mineral_IndicatorV2_SP",
}

# ArcGIS MapServers for Layer 3. All leaf layers of each service are queried.
POI_SERVICES = [
    "RSLs_Gullies_New_IcyCraters_clon0",
    "Aquieous_Mineral_Distribution_Options_clon0",  # sic: misspelled upstream
    "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0",
    "EZMars",
    "Dune_Field",
    "combinedNom",
    "SIM3292_Global_Geology",
    "mars_mro_crism_mtrdr_c0a_humex_frt_sites",
]


def make_session():
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=32))
    s.headers["User-Agent"] = "mars-map-data-fetch/1.0"
    return s


SESSION = make_session()


def write_atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


# ------------------------------------------------------------------ DEM
def fetch_dem(force):
    out = RAW / "dem" / "dem_blend200m_aoi.tif"
    if out.exists() and not force:
        print(f"[dem] exists, skipping: {out.relative_to(ROOT)}")
        return {"file": str(out.relative_to(ROOT)), "skipped": True}
    w, s, e, n = AOI
    params = {
        "bbox": f"{w},{s},{e},{n}", "bboxSR": 104905, "imageSR": 104905,
        "size": f"{DEM_WIDTH_PX},{int(DEM_WIDTH_PX * (n - s) / (e - w))}",
        "format": "tiff", "pixelType": "F32", "noData": -32767,
        "interpolation": "RSP_BilinearInterpolation", "f": "image",
    }
    r = SESSION.get(f"{ARC}/{DEM_SERVICE}/ImageServer/exportImage", params=params, timeout=300)
    r.raise_for_status()
    arr = tifffile.imread(io.BytesIO(r.content)).astype("float32")  # validates it is a real TIFF
    arr[arr <= -32000] = np.nan
    write_atomic(out, r.content)
    info = {"file": str(out.relative_to(ROOT)), "shape": list(arr.shape),
            "elev_min_m": float(np.nanmin(arr)), "elev_max_m": float(np.nanmax(arr)),
            "nodata_pct": round(float(100 * np.isnan(arr).mean()), 2)}
    print(f"[dem] {info}")
    return info


# ------------------------------------------------------------------ tiles
def wmts_caps(label):
    r = SESSION.get(WMTS.format(label=label), timeout=60)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    res = root.find(".//w:ResourceURL", NS)
    style = root.find(".//w:Style/ows:Identifier", NS)
    tms = root.find(".//w:TileMatrixSetLink/w:TileMatrixSet", NS)
    tmpl = (res.get("template")
            .replace("{Style}", style.text if style is not None else "default")
            .replace("{TileMatrixSet}", tms.text if tms is not None else "default028mm"))
    fmt = res.get("format", "image/png")
    ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg"}.get(fmt, "png")
    levels = {}
    for m in root.findall(".//w:Contents/w:TileMatrixSet/w:TileMatrix", NS):
        z = int(m.find("ows:Identifier", NS).text)
        levels[z] = 360.0 / float(m.find("w:MatrixWidth", NS).text)  # tile span in degrees
    return tmpl, ext, levels


def tile_range(deg, bbox):
    w, s, e, n = bbox
    return (int((90 - n) // deg), int((90 - s) // deg)), (int((w + 180) // deg), int((e + 180) // deg))


def fetch_tile(tmpl, ext, dest_root, z, r, c, force):
    dest = dest_root / str(z) / str(r) / f"{c}.{ext}"
    if dest.exists() and not force:
        return "cached"
    url = tmpl.replace("{TileMatrix}", str(z)).replace("{TileRow}", str(r)).replace("{TileCol}", str(c))
    try:
        resp = SESSION.get(url, timeout=60)
    except requests.exceptions.RetryError:
        return "unavailable"  # server keeps answering 5xx for this tile (known holes in some mosaics)
    except requests.RequestException:
        return "error"
    if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image") and resp.content:
        write_atomic(dest, resp.content)
        return "ok"
    return "missing"  # no coverage for this tile


def fetch_tiles(force, min_zoom, max_zoom, workers):
    report = {}
    for role, label in TILE_LAYERS.items():
        try:
            tmpl, ext, levels = wmts_caps(label)
        except Exception as e:  # noqa: BLE001
            print(f"[tiles] {label}: capabilities failed: {e}")
            report[label] = {"role": role, "error": str(e)[:200]}
            continue
        top = min(max_zoom, max(levels))
        jobs = []
        dest_root = RAW / "tiles" / label
        for z in range(min_zoom, top + 1):
            if z not in levels:
                continue
            (r0, r1), (c0, c1) = tile_range(levels[z], AOI)
            jobs += [(z, r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
        with cf.ThreadPoolExecutor(workers) as ex:
            results = list(ex.map(lambda j: fetch_tile(tmpl, ext, dest_root, *j, force), jobs))
        counts = {k: results.count(k) for k in ("ok", "cached", "missing", "unavailable", "error")}
        print(f"[tiles] {role} ({label}) z{min_zoom}-{top}: {len(jobs)} tiles {counts}")
        report[label] = {"role": role, "zoom": [min_zoom, top], "max_zoom_served": max(levels),
                         "ext": ext, "tiles": len(jobs), **counts}
    return report


# ------------------------------------------------------------------ POI vectors
def fetch_pois(force):
    out_dir = RAW / "features"
    report = {}
    for svc in POI_SERVICES:
        try:
            meta = SESSION.get(f"{ARC}/{svc}/MapServer", params={"f": "json"}, timeout=60).json()
            layers = [(l["id"], l["name"]) for l in meta.get("layers", []) if not l.get("subLayerIds")]
        except Exception as e:  # noqa: BLE001
            print(f"[pois] {svc}: failed to list layers: {e}")
            report[svc] = {"error": str(e)[:200]}
            continue
        for lid, lname in layers:
            dest = out_dir / f"{svc}__{lid}.geojson"
            key = f"{svc}/{lid}"
            if dest.exists() and not force:
                report[key] = {"name": lname, "skipped": True}
                continue
            params = {"f": "geojson", "where": "1=1", "outFields": "*", "returnGeometry": "true",
                      "geometry": ",".join(map(str, AOI)), "geometryType": "esriGeometryEnvelope",
                      "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
            try:
                gj = SESSION.get(f"{ARC}/{svc}/MapServer/{lid}/query", params=params, timeout=120).json()
            except Exception as e:  # noqa: BLE001
                report[key] = {"name": lname, "error": str(e)[:200]}
                print(f"[pois] {key} {lname}: ERROR {e}")
                continue
            n = len(gj.get("features", []))
            if n:
                write_atomic(dest, json.dumps(gj).encode())
            report[key] = {"name": lname, "features": n}
            print(f"[pois] {key} {lname}: {n} features")
    return report


# ------------------------------------------------------------------ MDAD
def fetch_mdad(force):
    out = RAW / "mdad" / "MDAD_original"
    if out.exists() and not force:
        print(f"[mdad] exists, skipping: {out.relative_to(ROOT)}")
        return {"file": str(out.relative_to(ROOT)), "skipped": True}
    r = SESSION.get(MDAD_URL, timeout=300)
    r.raise_for_status()
    head = r.content[:300].decode("utf-8", "replace")
    if "Mars Year" not in head:  # guard against an HTML error/login page
        raise RuntimeError(f"MDAD download does not look like the CSV: {head[:120]!r}")
    write_atomic(out, r.content)
    rows = r.content.count(b"\n") - 1
    print(f"[mdad] {rows} rows, {len(r.content) / 1e6:.1f} MB")
    return {"file": str(out.relative_to(ROOT)), "rows": rows}


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=["dem", "tiles", "pois", "mdad"],
                    help="fetch only these datasets (default: all)")
    ap.add_argument("--min-zoom", type=int, default=5)
    ap.add_argument("--max-zoom", type=int, default=9,
                    help="highest WMTS zoom to download (default 9; each level is ~4x the tiles)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = ap.parse_args()
    todo = args.only or ["dem", "tiles", "pois", "mdad"]

    manifest_path = RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest["aoi_bbox_w_s_e_n"] = AOI
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    t0 = time.time()
    failed = []
    steps = {
        "dem": lambda: fetch_dem(args.force),
        "tiles": lambda: fetch_tiles(args.force, args.min_zoom, args.max_zoom, args.workers),
        "pois": lambda: fetch_pois(args.force),
        "mdad": lambda: fetch_mdad(args.force),
    }
    for name in todo:
        try:
            manifest[name] = steps[name]()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] FAILED: {e}")
            failed.append(name)
    write_atomic(manifest_path, json.dumps(manifest, indent=1).encode())
    print(f"done in {time.time() - t0:.0f}s -> {manifest_path.relative_to(ROOT)}"
          + (f"  (failed: {', '.join(failed)})" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
