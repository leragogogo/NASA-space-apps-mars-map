"""`GraphInputs` taken from the layer getters (relief, weather, POI) through their public methods.

The graph therefore sees exactly what the map shows: the relief getter's own elevation and slope arrays
(no resampling, no second slope computation), the weather getter's display risk and message, and the
POI getter's features. Nothing here reads data/raw/ except to name the source files for staleness hashing.
"""
from __future__ import annotations

import numpy as np

from app.core.config import REPO_ROOT, Settings
from app.layers.base import LayerUnavailable
from app.layers.contracts import (SEASONS, Confidence, GraphInputs, GridSpec, LayerDataError, PoiData,
                                  PoiFeature, PoiKind, ReliefData, RiskLevel, WeatherData, WeatherFrame)
from app.layers.poi.normalize import DATASETS
from app.layers.registry import Registry
from app.layers.validate import validate_inputs
from app.layers.weather.getter import SEASONS as SEASON_BY_KEY

_RISK = {"Low": RiskLevel.LOW, "Moderate": RiskLevel.MODERATE, "High": RiskLevel.HIGH}
_CONFIDENCE = {"reliable": Confidence.RELIABLE, "approximate": Confidence.APPROXIMATE,
               "insufficient_data": Confidence.INSUFFICIENT_DATA}
# POI dataset (file stem, the prefix of the getter's feature id) -> PoiKind
_KIND = {
    "Aquieous_Mineral_Distribution_Options_clon0__0": PoiKind.MINERAL_HYDROUS,  # split by Class below
    "Hydrous_Mineral_Detections_OMEGA_CRISM_clon0__0": PoiKind.MINERAL_HYDROUS,
    "RSLs_Gullies_New_IcyCraters_clon0__0": PoiKind.RSL,
    "EZMars__0": PoiKind.EXPLORATION_ZONE, "EZMars__3": PoiKind.EXPLORATION_ROI,
    "EZMars__4": PoiKind.EXPLORATION_ZONE, "Dune_Field__0": PoiKind.DUNE_FIELD,
    "SIM3292_Global_Geology__0": PoiKind.GEOLOGY_UNIT, "combinedNom__0": PoiKind.NOMENCLATURE,
    "mars_mro_crism_mtrdr_c0a_humex_frt_sites__0": PoiKind.CRISM_SITE,
}
_SEASON_KEYS = tuple(k for s in SEASONS for k, v in SEASON_BY_KEY.items() if v == s)  # SEASONS order


def _rel(path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _block_mean(a: np.ndarray, f: int) -> np.ndarray:
    """f x f block mean, NaN-aware; NaN where fewer than half of the block's cells have data."""
    nr, nc = a.shape[0] // f, a.shape[1] // f
    blocks = a[:nr * f, :nc * f].reshape(nr, f, nc, f)
    ok = np.isfinite(blocks)
    count = ok.sum(axis=(1, 3))
    total = np.where(ok, blocks, 0.0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / count
    return np.where(count * 2 >= f * f, mean, np.nan)


def relief_from_getter(getter, coarsen: int = 1) -> ReliefData:
    """The getter's elevation and slope arrays, block-averaged by `coarsen` (1 = the getter's own 200 m grid).

    At 1 nothing is resampled, so the routed slope is exactly the displayed slope. A larger factor averages
    both arrays (no second slope is computed); remainder rows and columns on the south and east edges are
    dropped and the grid bbox shrinks to match.
    """
    if coarsen < 1:
        raise ValueError("coarsen must be >= 1")
    g = getter.grid()
    elev, slope = np.asarray(g["elevation_m"], dtype=np.float64), np.asarray(g["slope_deg"], dtype=np.float64)
    west, south, east, north = g["aoi"]
    nrows, ncols = elev.shape
    dlon, dlat = (east - west) / ncols, (north - south) / nrows
    if coarsen > 1:
        elev, slope = _block_mean(elev, coarsen), _block_mean(slope, coarsen)
    rows, cols = elev.shape
    grid = GridSpec(west, north - rows * coarsen * dlat, west + cols * coarsen * dlon, north, ncols=cols, nrows=rows)
    valid = np.isfinite(elev)
    slope = np.where(valid, np.nan_to_num(slope, nan=0.0), np.nan)  # a valid node always has a slope
    return ReliefData(grid=grid, elev_m=elev.astype(np.float32), valid=valid, slope_deg=slope.astype(np.float32))


def _cell_box(feature: dict) -> tuple[float, float, float, float]:
    ring = np.asarray(feature["geometry"]["coordinates"][0], dtype=float)
    return (round(float(ring[:, 0].min()), 6), round(float(ring[:, 1].min()), 6),
            round(float(ring[:, 0].max()), 6), round(float(ring[:, 1].max()), 6))


def weather_from_getter(getter, grid: GridSpec) -> WeatherData:
    """Per-node display risk and confidence from the getter's 1 deg cells; frames keep their `message`."""
    caveat = str(getter.describe(_SEASON_KEYS[0]).get("caveat", "")).strip()
    boxes: dict[tuple, int] = {}
    by_season: list[dict] = []
    for key, season in zip(_SEASON_KEYS, SEASONS):
        for f in getter.cells(key):
            k = boxes.setdefault(_cell_box(f), len(boxes))
            if k == len(by_season):
                by_season.append({})
            by_season[k][season] = dict(f["properties"])
    frames = tuple(WeatherFrame(frame_idx=k, west=b[0], south=b[1], east=b[2], north=b[3], by_season=by_season[k])
                   for b, k in boxes.items())
    cell_risk = np.full((len(SEASONS), len(frames)), int(RiskLevel.NONE), dtype=np.int8)
    cell_conf = np.full((len(SEASONS), len(frames)), int(Confidence.INSUFFICIENT_DATA), dtype=np.int8)
    for k, fr in enumerate(frames):
        for s, season in enumerate(SEASONS):
            p = fr.by_season.get(season)
            if p is None:
                continue
            cell_risk[s, k] = int(_RISK.get(p.get("display_risk"), RiskLevel.NONE))
            cell_conf[s, k] = int(_CONFIDENCE.get(p.get("confidence"), Confidence.INSUFFICIENT_DATA))
    lon, lat = grid.node_lonlat()
    frame_idx = np.full(lon.shape, -1, dtype=np.int32)
    for k, fr in enumerate(frames):  # restrict to cells that can touch the grid
        if fr.east < grid.west or fr.west > grid.east or fr.north < grid.south or fr.south > grid.north:
            continue
        inside = (lon >= fr.west) & (lon < fr.east) & (lat >= fr.south) & (lat < fr.north) & (frame_idx < 0)
        frame_idx[inside] = k
    has, safe = frame_idx >= 0, np.where(frame_idx >= 0, frame_idx, 0)
    risk = np.where(has[None, :], cell_risk[:, safe], int(RiskLevel.NONE)).astype(np.int8)
    conf = np.where(has[None, :], cell_conf[:, safe], int(Confidence.INSUFFICIENT_DATA)).astype(np.int8)
    shape3 = (len(SEASONS), *grid.shape)
    return WeatherData(grid=grid, seasons=SEASONS, risk=risk.reshape(shape3), confidence=conf.reshape(shape3),
                       frame_idx=frame_idx.reshape(grid.shape), frames=frames, caveat=caveat)


def _poi_kind(feature: dict) -> PoiKind:
    stem = feature["properties"]["id"].rsplit(":", 1)[0]
    if stem == "Aquieous_Mineral_Distribution_Options_clon0__0":
        cls = str((feature["properties"].get("raw") or {}).get("Class") or "").lower()
        if "silica" in cls:
            return PoiKind.MINERAL_SILICA
        if "sulf" in cls:
            return PoiKind.MINERAL_SULFATE
    return _KIND[stem]


def poi_from_getter(getter) -> PoiData:
    """The getter's features as PoiFeatures. The optional nearest-POI node arrays are left out."""
    out, used = [], set()
    for f in getter.features():
        if not f.get("geometry"):
            continue
        pr = f["properties"]
        pid = pr["id"] if pr["id"] not in used else f"{pr['id']}#{len(used)}"
        used.add(pid)
        out.append(PoiFeature(id=pid, kind=_poi_kind(f), geometry=f["geometry"], source=pr.get("source", ""),
                              name=pr.get("name") or None,
                              properties={"description": pr.get("description", ""), "category": pr["category"]}))
    return PoiData(features=tuple(out))


def _source_files(settings: Settings) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    raw = settings.raw_dir
    dem = (_rel(raw / "dem" / "dem_blend200m_aoi.tif"),)
    weather = tuple(_rel(raw / "weather" / n) for n in ("context_weather_frames.geojson", "aoi_weather_frames.json"))
    poi = tuple(_rel(p) for p in sorted((raw / "features").glob("*.geojson")) if p.stem in DATASETS)
    return dem, weather, poi


def graph_inputs_from_registry(registry: Registry, settings: Settings | None = None,
                               coarsen: int = 1) -> GraphInputs:
    """Validated `GraphInputs` from the relief, weather and POI getters of a built registry.

    Raises LayerDataError (with the script to run) when one of those layers is unavailable.
    """
    settings = settings or Settings()
    try:
        relief, weather, poi = registry.get("relief"), registry.get("weather"), registry.get("poi")
    except LayerUnavailable as ex:
        raise LayerDataError("getters", f"{ex.detail}; fix: {ex.fix}") from ex
    r = relief_from_getter(relief, coarsen)
    w = weather_from_getter(weather, r.grid)
    p = poi_from_getter(poi)
    dem_files, weather_files, poi_files = _source_files(settings)
    inputs = GraphInputs(grid=r.grid,
                         relief=ReliefData(r.grid, r.elev_m, r.valid, r.slope_deg, None, dem_files),
                         weather=WeatherData(w.grid, w.seasons, w.risk, w.confidence, w.frame_idx, w.frames,
                                             w.caveat, weather_files),
                         poi=PoiData(p.features, None, None, poi_files))
    validate_inputs(inputs)
    return inputs
