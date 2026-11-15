"""Layer 1 service: catalog JSON the frontend uses to build its layer list. Tiles are served by /api/tiles."""
from __future__ import annotations

from app.layers.contracts import ImageryCatalog

DEFAULT_SOURCE = "ctx_coprates"


class BaseImageryGetter:
    name = "base_imagery"

    def __init__(self, settings, catalog: ImageryCatalog):
        self.catalog = catalog
        id_of = {d.folder: sid for sid, d in settings.tile_sources.items()}
        notes = {sid: d.coverage_note for sid, d in settings.tile_sources.items()}
        self._folder_of = {sid: folder for folder, sid in id_of.items()}
        by_id = {}
        for info in catalog.layers:
            sid = id_of[info.id]
            w, s, e, n = info.bounds
            by_id[sid] = {"id": sid, "title": info.label, "tile_url": f"/api/tiles/{sid}/{{z}}/{{y}}/{{x}}",
                          "format": info.ext, "tile_size": info.tile_size, "min_zoom": info.min_zoom,
                          "max_zoom": info.max_zoom, "bounds": [[s, w], [n, e]], "coverage_note": notes[sid],
                          "role": info.role}
        # config order, like the tile table
        self._sources = [by_id[sid] for sid in settings.tile_sources if sid in by_id]

    def sources(self) -> list[dict]:
        return self._sources

    def describe(self) -> dict:
        ids = [s["id"] for s in self._sources]
        return {"layer": self.name, "default_source": DEFAULT_SOURCE if DEFAULT_SOURCE in ids else ids[0],
                "sources": self._sources}

    def tile_path(self, source_id: str, z: int, row: int, col: int):
        folder = self._folder_of.get(source_id)
        return None if folder is None else self.catalog.tile_path(folder, z, row, col)

    def sample(self, lon: float, lat: float, season: str | None = None):
        return None
