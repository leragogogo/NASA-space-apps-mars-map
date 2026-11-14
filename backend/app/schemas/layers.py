"""API models for the layer endpoints (catalog and point queries). GeoJSON layers are returned
as plain dicts built by each layer's service.py."""
from __future__ import annotations

from pydantic import BaseModel


class ImageryLayerOut(BaseModel):
    id: str
    role: str
    tile_size: int
    ext: str
    min_zoom: int
    max_zoom: int
    bounds: tuple[float, float, float, float]  # west, south, east, north


class LayerCatalogOut(BaseModel):
    imagery: list[ImageryLayerOut]
    seasons: list[str]
    aoi_bounds: tuple[float, float, float, float]


class ElevationOut(BaseModel):
    lon: float
    lat: float
    elev_m: float | None  # None = nodata
    slope_deg: float | None
