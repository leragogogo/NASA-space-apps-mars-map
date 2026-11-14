"""Layer 1: base imagery. Lists the imagery tile sources on disk; tiles are served by /api/tiles."""
from __future__ import annotations

from app.layers.base import LayerUnavailable
from app.tiles.store import TileStore

DEFAULT_SOURCE = "ctx_coprates"


class BaseImageryGetter:
    name = "base_imagery"

    def __init__(self, store: TileStore):
        self._store = store
        self._sources = store.available("base_imagery")
        if not self._sources:
            raise LayerUnavailable("No base imagery tiles found under data/raw/tiles.",
                                   "python scripts/download_data.py --only tiles")

    def sources(self) -> list[dict]:
        return self._sources

    def describe(self) -> dict:
        ids = [s["id"] for s in self._sources]
        return {"layer": self.name, "default_source": DEFAULT_SOURCE if DEFAULT_SOURCE in ids else ids[0],
                "sources": self._sources}

    def tile_path(self, source_id: str, z: int, row: int, col: int):
        return self._store.path(source_id, z, row, col)

    def sample(self, lon: float, lat: float, season: str | None = None):
        return None
