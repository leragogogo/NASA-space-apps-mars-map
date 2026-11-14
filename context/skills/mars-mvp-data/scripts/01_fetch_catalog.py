"""Step 1: Pull the full Mars Trek WMTS layer catalog (all 3 projections) and save it.

Uses the same catalog endpoints the Trek API doc page calls:
https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
"""
import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
(ROOT / "outputs").mkdir(parents=True, exist_ok=True)

BASE = "https://trek.nasa.gov/mars/TrekServices/ws/index/{ptype}/searchItems"
PROJ = {
    "eq": ("eq", "urn:ogc:def:crs:IAU2000::104905"),
    "np": ("polar", "urn:ogc:def:crs:IAU2000::49918"),
    "sp": ("polar", "urn:ogc:def:crs:IAU2000::49920"),
}
# Wider than the doc page: we do NOT exclude DEM/Slope/Confidence products
PARAMS = dict(start=0, rows=100000, facetKeys="itemType|serviceTypes", facetValues="product|Mosaic")


def main():
    rows = []
    for key, (ptype, proj) in PROJ.items():
        r = requests.get(BASE.format(ptype=ptype), params={**PARAMS, "proj": proj}, timeout=120)
        r.raise_for_status()
        docs = r.json()["response"]["docs"]
        (RAW / f"catalog_{key}.json").write_text(json.dumps(docs, indent=1))
        print(f"{key}: {len(docs)} layers")
        for d in docs:
            w, so, e, n = (float(v) for v in d["bbox"].split(","))
            ep = (d.get("services") or [{}])[0].get("endPoint")
            rows.append(dict(
                proj=key, title=d.get("title"), label=d.get("productLabel"),
                productType=d.get("productType"), cat1=d.get("productCat1"), cat2=d.get("productCat2"),
                instrument=d.get("instrument"), mission=d.get("mission"),
                resolution=float(d.get("resolution") or 0), coverage=d.get("coverage"),
                serviceTypes=d.get("serviceTypes"), uuid=d.get("item_UUID"), endpoint=ep,
                west=w, south=so, east=e, north=n, area_deg2=(e - w) * (n - so),
                description=(d.get("description") or "")[:400],
            ))
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "outputs" / "catalog_all.csv", index=False)
    print("keys of one doc:", sorted(docs[0].keys()))


if __name__ == "__main__":
    main()
