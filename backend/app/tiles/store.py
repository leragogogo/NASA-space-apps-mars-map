"""Finds tile files on disk. Only sources listed in the config tile-source table are ever served."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg"}


class TileStore:
    def __init__(self, tiles_dir: Path, sources: dict, aoi: tuple):
        self._dir = tiles_dir
        self._defs = sources
        w, s, e, n = aoi
        bounds = [[s, w], [n, e]]  # Leaflet order: [[south, west], [north, east]]
        self._info: dict[str, dict] = {}
        for sid, d in sources.items():
            folder = tiles_dir / d.folder
            if not folder.is_dir():
                continue
            zooms = sorted(int(p.name) for p in folder.iterdir() if p.is_dir() and p.name.isdigit())
            first = next((f for f in sorted(folder.rglob("*")) if f.suffix in (".png", ".jpg")), None)
            if not zooms or first is None:
                continue
            with Image.open(first) as im:
                size = im.size[0]
            self._info[sid] = {
                "id": sid, "title": d.title, "tile_url": f"/api/tiles/{sid}/{{z}}/{{y}}/{{x}}",
                "format": first.suffix[1:], "tile_size": size, "min_zoom": zooms[0], "max_zoom": zooms[-1],
                "bounds": [list(b) for b in bounds], "coverage_note": d.coverage_note,
            }

    def available(self, layer: str) -> list[dict]:
        """Tile sources of one layer that exist on disk, in config order."""
        return [info for sid, info in self._info.items() if self._defs[sid].layer == layer]

    def info(self, source_id: str) -> dict | None:
        return self._info.get(source_id)

    def path(self, source_id: str, z: int, row: int, col: int) -> tuple[Path, str] | None:
        """(file, media type) of one tile, or None if the source is unknown or the tile does not exist."""
        info = self._info.get(source_id)
        if info is None or min(z, row, col) < 0:
            return None
        p = self._dir / self._defs[source_id].folder / str(z) / str(row) / f"{col}.{info['format']}"
        return (p, MEDIA_TYPES[info["format"]]) if p.is_file() else None
