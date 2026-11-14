"""Step 2: For every catalog layer, check whether its WMTS tile service actually answers,
and record format / zoom levels / max resolution from WMTSCapabilities.xml."""
import concurrent.futures as cf
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
PDIR = {"eq": "EQ", "np": "NP", "sp": "SP"}
NS = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}


def probe(row):
    url = f"https://trek.nasa.gov/tiles/Mars/{PDIR[row.proj]}/{row.label}/1.0.0/WMTSCapabilities.xml"
    out = dict(label=row.label, proj=row.proj, wmts_url=url, wmts_ok=False)
    try:
        r = requests.get(url, timeout=60)
        if r.status_code != 200 or b"Capabilities" not in r.content[:2000]:
            return out
        root = ET.fromstring(r.content)
        res = root.find(".//w:ResourceURL", NS)
        tms = root.findall(".//w:Contents/w:TileMatrixSet/w:TileMatrix", NS)
        last = tms[-1] if tms else None
        # true ground resolution at max zoom: tile span (deg) / tile px * metres per degree on Mars
        mpp = (360.0 / float(last.find("w:MatrixWidth", NS).text) / int(last.find("w:TileWidth", NS).text)
               * 59274.7) if last is not None else None
        out.update(wmts_ok=True, template=res.get("template") if res is not None else None,
                   fmt=res.get("format") if res is not None else None,
                   zoom_levels=len(tms), best_m_per_px=round(mpp, 2) if mpp else None)
    except Exception as e:  # noqa
        out["err"] = str(e)[:100]
    return out


def main():
    df = pd.read_csv(ROOT / "outputs" / "catalog_all.csv")
    with cf.ThreadPoolExecutor(16) as ex:
        res = list(ex.map(probe, df.itertuples()))
    p = pd.DataFrame(res)
    m = df.merge(p, on=["label", "proj"], how="left")
    m.to_csv(ROOT / "outputs" / "catalog_with_services.csv", index=False)
    print(m.wmts_ok.value_counts())
    print(m[~m.wmts_ok][["proj", "title", "label"]].to_string())


if __name__ == "__main__":
    main()
