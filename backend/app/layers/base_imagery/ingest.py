"""Base-imagery ingestion: data/raw/tiles/<label>/... -> ImageryCatalog (layer-ingestion.md section 4).

Not an input to the graph. Only the base-imagery sources of the config tile table are listed.
"""
from __future__ import annotations

from app.layers.contracts import ImageryCatalog, ImageryLayerInfo, LayerDataError
from app.tiles.store import TileStore

FIX = "Run `python scripts/download_data.py --only tiles`."
ROLES = {"ctx_coprates": "primary", "ctx_global": "fallback", "hirise": "zoom-in detail"}


def ingest_imagery(settings, store: TileStore | None = None) -> ImageryCatalog:
    store = store or TileStore(settings.raw_dir / "tiles", settings.tile_sources, settings.aoi)
    w, s, e, n = settings.aoi
    layers = []
    for info in store.available("base_imagery"):
        folder = settings.tile_sources[info["id"]].folder
        layers.append(ImageryLayerInfo(id=folder, label=info["title"], role=ROLES.get(info["id"], "other"),
                                       tile_size=info["tile_size"], ext=info["format"],
                                       min_zoom=info["min_zoom"], max_zoom=info["max_zoom"], bounds=(w, s, e, n)))
    if not layers:
        raise LayerDataError("base_imagery", f"No base imagery tiles found under {settings.raw_dir / 'tiles'}. {FIX}")
    return ImageryCatalog(root=settings.raw_dir / "tiles", layers=tuple(layers))
