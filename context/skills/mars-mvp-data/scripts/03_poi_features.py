"""Step 3: Query the Trek ArcGIS MapServer vector layers (points of interest: minerals, ice,
glaciers, gullies, RSLs, geology, etc.) and count features inside each candidate demo region."""
import json
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "features"
RAW.mkdir(parents=True, exist_ok=True)
ARC = "https://trek.nasa.gov/mars/trekarcgis/rest/services"

# Candidate regions = places where the catalog shows clusters of local high-res products.
# bbox = (west, south, east, north), longitudes in -180..180
REGIONS = {
    "East Melas / Coprates (Valles Marineris)": (-71.8, -16.5, -66.0, -9.5),
    "West Candor Chasma": (-78.0, -7.0, -76.0, -4.5),
    "Jezero Crater": (76.0, 17.0, 78.5, 19.5),
    "Gale Crater (Curiosity)": (136.5, -6.0, 138.5, -3.5),
    "Gusev / Columbia Hills / Apollinaris": (174.5, -15.5, 179.0, -11.5),
    "Deuteronilus Mensae": (20.0, 36.0, 26.5, 42.5),
    "Meridiani / Endeavour (Opportunity)": (-7.0, -4.0, -4.0, -1.0),
    "InSight / Elysium": (134.0, 3.0, 137.5, 6.0),
    "Mawrth Vallis": (-21.0, 22.0, -17.0, 26.0),
}

POI_SERVICES = [
    "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0",
    "Aquieous_Mineral_Distribution_Options_clon0",
    "Chloride_Salt_bearing_Material_THEMIS_clon0",
    "RSLs_Gullies_New_IcyCraters_clon0",
    "Mars_Fans_Glaciers_Gullies",
    "Dune_Field",
    "Hynek_Valley_Networks",
    "SIM3292_Global_Geology",
    "EZMars",
    "mars_mro_crism_mtrdr_c0a_humex_frt_sites",
    "major_features",
    "combinedNom",
]


def layers_of(svc):
    r = requests.get(f"{ARC}/{svc}/MapServer", params={"f": "json"}, timeout=60).json()
    return [(l["id"], l["name"]) for l in r.get("layers", []) if not l.get("subLayerIds")]


def query(svc, lid, bbox):
    params = {
        "f": "geojson", "where": "1=1", "outFields": "*", "returnGeometry": "true",
        "geometry": ",".join(map(str, bbox)), "geometryType": "esriGeometryEnvelope",
        "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
    }
    r = requests.get(f"{ARC}/{svc}/MapServer/{lid}/query", params=params, timeout=120)
    try:
        return r.json()
    except Exception:
        return {"error": r.text[:200]}


def main():
    rows = []
    for svc in POI_SERVICES:
        try:
            lyrs = layers_of(svc)
        except Exception as e:
            print("FAIL", svc, e); continue
        for lid, lname in lyrs:
            for reg, bbox in REGIONS.items():
                gj = query(svc, lid, bbox)
                n = len(gj.get("features", [])) if "features" in gj else None
                if n:
                    fn = RAW / f"{svc}__{lid}__{reg.split()[0].strip('/')}.geojson"
                    fn.write_text(json.dumps(gj))
                rows.append(dict(service=svc, layer_id=lid, layer=lname, region=reg, n_features=n,
                                 err=None if n is not None else str(gj)[:120]))
            print(f"{svc}/{lid} {lname}: done")
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "outputs" / "poi_counts_long.csv", index=False)
    piv = df.pivot_table(index=["service", "layer"], columns="region", values="n_features", aggfunc="sum")
    piv.to_csv(ROOT / "outputs" / "poi_counts_by_region.csv")
    pd.set_option("display.width", 300)
    print(piv.T.to_string())


if __name__ == "__main__":
    main()
