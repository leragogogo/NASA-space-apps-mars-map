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


class TileSource(BaseModel):
    id: str
    title: str
    tile_url: str
    format: str
    tile_size: int
    min_zoom: int
    max_zoom: int
    bounds: list[list[float]]
    coverage_note: str
    role: str | None = None  # base imagery only: primary | fallback | zoom-in detail


class LayerOneResponse(BaseModel):
    layer: str
    default_source: str
    sources: list[TileSource]


class SlopeClassOut(BaseModel):
    id: str
    label: str
    min_deg: float
    max_deg: float
    color: str
    walkable: bool
    vehicle: bool


class Overlay(BaseModel):
    url: str
    bounds: list[list[float]]


class LayerTwoResponse(BaseModel):
    layer: str
    bounds: list[list[float]]
    resolution_m: int
    elevation_range_m: list[int]
    slope_classes: list[SlopeClassOut]
    overlay: Overlay
    hillshade_sources: list[TileSource]
    caveats: list[str]


class PointResponse(BaseModel):
    lon: float
    lat: float
    elevation_m: float | None
    slope_deg: float | None
    slope_class: str | None
    walkable: bool
    vehicle: bool
    approximate: bool
