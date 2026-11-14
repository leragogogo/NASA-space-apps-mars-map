"""Data contracts between layer ingestion, the graph builder and the API.

Each layer's `ingest.py` turns data/raw/ files into one of the *Data classes below, aligned
to a shared `GridSpec`. The graph builder consumes only `GraphInputs` and never reads
data/raw/ itself. Spec: context/skills/mars-mvp-data/references/layer-ingestion.md.
Conventions: lon -180..180, SI units, row 0 = north row, NaN = nodata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, Mapping

import numpy as np

MARS_RADIUS_M = 3_396_190.0  # Mars 2000 sphere (IAU2000:104905)
AOI_BBOX = (-71.8, -13.4, -68.0, -10.0)  # west, south, east, north: East Melas / Coprates
AOI_DEM_SHAPE = (1073, 1200)  # (rows, cols) of data/raw/dem/dem_blend200m_aoi.tif

SEASONS: tuple[str, ...] = (
    "S. Autumn (Ls 0-90)",
    "S. Winter (Ls 90-180)",
    "S. Spring (Ls 180-270, perihelion)",
    "S. Summer (Ls 270-360)",
)


class RiskLevel(IntEnum):
    NONE = -1  # no estimate possible
    LOW = 0
    MODERATE = 1
    HIGH = 2


class Confidence(IntEnum):
    RELIABLE = 0
    APPROXIMATE = 1
    INSUFFICIENT_DATA = 2


class PoiKind(StrEnum):
    RSL = "rsl"
    MINERAL_SULFATE = "mineral_sulfate"
    MINERAL_SILICA = "mineral_silica"
    MINERAL_HYDROUS = "mineral_hydrous"
    DUNE_FIELD = "dune_field"
    EXPLORATION_ZONE = "exploration_zone"
    EXPLORATION_ROI = "exploration_roi"
    CRISM_SITE = "crism_site"
    NOMENCLATURE = "nomenclature"
    GEOLOGY_UNIT = "geology_unit"
    SHELTER_CANDIDATE = "shelter_candidate"  # reserved; not produced yet


class LayerDataError(Exception):
    """Raised by ingestion and validation. A missing file says: run scripts/download_data.py."""

    def __init__(self, layer: str, message: str):
        super().__init__(f"[{layer}] {message}")
        self.layer = layer
        self.message = message


# --------------------------------------------------------------------------- grid
@dataclass(frozen=True)
class GridSpec:
    """The one grid every layer is resampled to and the graph is built on.

    Cells are indexed (row, col) with row 0 = north row; node id = row * ncols + col.
    Nodes sit at cell centres.
    """

    west: float
    south: float
    east: float
    north: float
    ncols: int
    nrows: int
    radius_m: float = MARS_RADIUS_M

    def __post_init__(self):
        if not (self.east > self.west and self.north > self.south):
            raise ValueError("bbox must satisfy east > west and north > south")
        if self.ncols < 1 or self.nrows < 1:
            raise ValueError("ncols and nrows must be >= 1")
        if not (-180.0 <= self.west and self.east <= 180.0):
            raise ValueError("longitude must be within -180..180")

    @property
    def shape(self) -> tuple[int, int]:
        return (self.nrows, self.ncols)

    @property
    def n_nodes(self) -> int:
        return self.nrows * self.ncols

    @property
    def dlon(self) -> float:
        return (self.east - self.west) / self.ncols

    @property
    def dlat(self) -> float:
        return (self.north - self.south) / self.nrows

    def node_id(self, row, col):
        return np.asarray(row) * self.ncols + np.asarray(col)

    def rc(self, node_id):
        row, col = np.divmod(np.asarray(node_id), self.ncols)
        return row, col

    def lon_centers(self) -> np.ndarray:
        return self.west + (np.arange(self.ncols) + 0.5) * self.dlon

    def lat_centers(self) -> np.ndarray:
        return self.north - (np.arange(self.nrows) + 0.5) * self.dlat

    def node_lonlat(self) -> tuple[np.ndarray, np.ndarray]:
        """(lon, lat) of every node, flat arrays of length n_nodes in node-id order."""
        return np.tile(self.lon_centers(), self.nrows), np.repeat(self.lat_centers(), self.ncols)

    def contains(self, lon, lat):
        lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
        return (lon >= self.west) & (lon <= self.east) & (lat >= self.south) & (lat <= self.north)

    def lonlat_to_rc(self, lon, lat):
        """(row, col) of the cell holding each point; (-1, -1) for points outside the grid."""
        lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
        inside = self.contains(lon, lat)
        with np.errstate(invalid="ignore"):
            col = np.minimum(np.floor((lon - self.west) / self.dlon), self.ncols - 1)
            row = np.minimum(np.floor((self.north - lat) / self.dlat), self.nrows - 1)
        col = np.where(inside, col, -1).astype(int)
        row = np.where(inside, row, -1).astype(int)
        return row, col

    def metric_spacing(self) -> tuple[np.ndarray, float]:
        """(dx_m per row, dy_m): cell size in metres. dx shrinks with cos(latitude)."""
        dy = np.radians(self.dlat) * self.radius_m
        dx = np.radians(self.dlon) * self.radius_m * np.cos(np.radians(self.lat_centers()))
        return dx, float(dy)

    @classmethod
    def from_bbox(cls, bbox: tuple[float, float, float, float], cell_m: float) -> "GridSpec":
        west, south, east, north = bbox
        mid = np.radians((south + north) / 2)
        width_m = np.radians(east - west) * MARS_RADIUS_M * np.cos(mid)
        height_m = np.radians(north - south) * MARS_RADIUS_M
        return cls(west, south, east, north,
                   ncols=max(1, round(width_m / cell_m)), nrows=max(1, round(height_m / cell_m)))

    def to_dict(self) -> dict[str, Any]:
        return {"west": self.west, "south": self.south, "east": self.east, "north": self.north,
                "ncols": self.ncols, "nrows": self.nrows, "radius_m": self.radius_m}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "GridSpec":
        return cls(float(d["west"]), float(d["south"]), float(d["east"]), float(d["north"]),
                   int(d["ncols"]), int(d["nrows"]), float(d.get("radius_m", MARS_RADIUS_M)))


def default_grid(coarsen: int = 2) -> GridSpec:
    """AOI bbox, with the 200 m DEM shape divided by `coarsen` (2 -> ~400 m, ~320k nodes)."""
    if coarsen < 1:
        raise ValueError("coarsen must be >= 1")
    rows, cols = AOI_DEM_SHAPE
    return GridSpec(*AOI_BBOX, ncols=cols // coarsen, nrows=rows // coarsen)


# --------------------------------------------------------------------------- relief
@dataclass(frozen=True, eq=False)
class ReliefData:
    """elev_m / slope_deg: float32 (nrows, ncols), NaN = nodata; valid: bool mask.

    slope_deg is computed once (app.layers.relief.slope.slope_deg) from elev_m; the graph
    builder derives signed edge gradients from the same elev_m.
    """

    grid: GridSpec
    elev_m: np.ndarray
    valid: np.ndarray
    slope_deg: np.ndarray
    roughness_m: np.ndarray | None = None
    source_files: tuple[str, ...] = ()


# --------------------------------------------------------------------------- points of interest
@dataclass(frozen=True)
class PoiFeature:
    id: str  # stable: "<service>:<layer_id>:<objectid-or-index>"
    kind: PoiKind
    geometry: Mapping[str, Any]  # GeoJSON Point / Polygon / MultiPolygon, lon -180..180
    source: str  # "service/layer"
    name: str | None = None
    properties: Mapping[str, Any] = field(default_factory=dict)

    def lonlat(self) -> tuple[float, float]:
        """Representative point: the point itself, or the mean of the (first) exterior ring."""
        g = self.geometry
        kind, coords = g.get("type"), g.get("coordinates")
        if kind == "Point":
            return float(coords[0]), float(coords[1])
        ring = None
        if kind == "Polygon":
            ring = coords[0]
        elif kind == "MultiPolygon":
            ring = coords[0][0]
        if ring is None:
            raise ValueError(f"unsupported geometry type {kind!r}")
        pts = np.asarray(ring, dtype=float)
        return float(pts[:, 0].mean()), float(pts[:, 1].mean())


@dataclass(frozen=True, eq=False)
class PoiData:
    features: tuple[PoiFeature, ...]
    nearest_poi_dist_m: np.ndarray | None = None  # float32 (nrows, ncols), optional
    nearest_poi_id: np.ndarray | None = None  # int32 (nrows, ncols), index into features, -1 = none
    source_files: tuple[str, ...] = ()

    def _select(self, kinds):
        wanted = None if kinds is None else {PoiKind(k) for k in kinds}
        return [f for f in self.features if wanted is None or f.kind in wanted]

    def as_geojson(self, kinds=None) -> dict[str, Any]:
        return {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": f.id, "geometry": dict(f.geometry),
             "properties": {**f.properties, "kind": f.kind.value, "name": f.name, "source": f.source}}
            for f in self._select(kinds)]}

    def points(self, kinds=None) -> list[tuple[str, PoiKind, float, float]]:
        """(id, kind, lon, lat) of every selected feature: destination candidates."""
        return [(f.id, f.kind, *f.lonlat()) for f in self._select(kinds)]


# --------------------------------------------------------------------------- weather
@dataclass(frozen=True)
class WeatherFrame:
    """One 1 deg cell: the full per-season frame properties (incl. `message`) from the source."""

    frame_idx: int
    west: float
    south: float
    east: float
    north: float
    by_season: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True, eq=False)
class WeatherData:
    """risk / confidence: int8 (4, nrows, ncols), season order = SEASONS.

    risk is the display risk (typical_year_risk, else risk, else neighbour estimate, else NONE).
    Season never enters edge weights; these arrays back warnings and node attributes.
    """

    grid: GridSpec
    seasons: tuple[str, ...]
    risk: np.ndarray
    confidence: np.ndarray
    frame_idx: np.ndarray  # int32 (nrows, ncols), -1 = no frame
    frames: tuple[WeatherFrame, ...]
    caveat: str
    source_files: tuple[str, ...] = ()

    def season_index(self, season: str) -> int:
        try:
            return self.seasons.index(season)
        except ValueError:
            raise ValueError(f"unknown season {season!r}; expected one of {self.seasons}") from None

    def frame_at(self, lon: float, lat: float, season: str) -> Mapping[str, Any] | None:
        """Full frame properties (with `message`) for the point and season, or None if outside."""
        self.season_index(season)
        row, col = self.grid.lonlat_to_rc(lon, lat)
        if int(row) < 0:
            return None
        idx = int(self.frame_idx[int(row), int(col)])
        return None if idx < 0 else self.frames[idx].by_season.get(season)

    def risk_at(self, lon: float, lat: float, season: str) -> tuple[RiskLevel, Confidence]:
        s = self.season_index(season)
        row, col = self.grid.lonlat_to_rc(lon, lat)
        if int(row) < 0:
            return RiskLevel.NONE, Confidence.INSUFFICIENT_DATA
        return (RiskLevel(int(self.risk[s, int(row), int(col)])),
                Confidence(int(self.confidence[s, int(row), int(col)])))


# --------------------------------------------------------------------------- imagery
@dataclass(frozen=True)
class ImageryLayerInfo:
    id: str  # the WMTS label; also the folder name under data/raw/tiles/
    label: str
    role: str
    tile_size: int  # 512 for CTX global and HiRISE, else 256
    ext: str
    min_zoom: int
    max_zoom: int
    bounds: tuple[float, float, float, float]  # west, south, east, north


@dataclass(frozen=True)
class ImageryCatalog:
    root: Path  # data/raw/tiles
    layers: tuple[ImageryLayerInfo, ...]

    def layer(self, layer_id: str) -> ImageryLayerInfo:
        for info in self.layers:
            if info.id == layer_id:
                return info
        raise KeyError(layer_id)

    def tile_path(self, layer_id: str, z: int, row: int, col: int) -> Path | None:
        """Path of the stored tile, or None when it was not downloaded (answer 404)."""
        info = self.layer(layer_id)
        path = self.root / info.id / str(z) / str(row) / f"{col}.{info.ext}"
        return path if path.is_file() else None


# --------------------------------------------------------------------------- bundle for the graph
@dataclass(frozen=True, eq=False)
class GraphInputs:
    """Everything the graph builder receives (produced by a future app.layers.load_all)."""

    grid: GridSpec
    relief: ReliefData
    weather: WeatherData
    poi: PoiData

    def __post_init__(self):
        for name in ("relief", "weather"):
            if getattr(self, name).grid != self.grid:
                raise LayerDataError("graph_inputs", f"{name}.grid does not match the graph grid")
