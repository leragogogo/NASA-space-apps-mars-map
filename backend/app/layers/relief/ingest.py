"""Relief ingestion: data/raw/dem -> ReliefData on the shared GridSpec (layer-ingestion.md section 4).

Elevation is block-averaged (NaN-aware) onto the grid; slope is computed once from that resampled
elevation, so the overlay shown to users and the slope used by the router are the same array.
"""
from __future__ import annotations

import hashlib

import numpy as np
import tifffile

from app.layers.contracts import AOI_DEM_SHAPE, GridSpec, LayerDataError, ReliefData
from app.layers.relief.roughness import roughness_m
from app.layers.relief.slope import slope_deg
from app.layers.validate import validate_relief

NODATA_BELOW = -32000  # Trek exports noData as -32767
FIX = "Run `python scripts/download_data.py --only dem`."


def dem_path(settings):
    return settings.raw_dir / "dem" / "dem_blend200m_aoi.tif"


def grid_for(settings) -> GridSpec:
    """The shared grid: the AOI bbox with the DEM shape divided by `settings.grid_coarsen`.
    Falls back to the known DEM shape when the file is missing, so other layers still get a grid."""
    if settings.grid_coarsen < 1:
        raise ValueError("grid_coarsen must be >= 1")
    path = dem_path(settings)
    try:
        with tifffile.TiffFile(path) as tif:
            rows, cols = tif.pages[0].shape[:2]
    except Exception:  # noqa: BLE001 - missing or unreadable: ingest_relief reports it properly
        rows, cols = AOI_DEM_SHAPE
    return GridSpec(*settings.aoi, ncols=max(cols // settings.grid_coarsen, 1),
                    nrows=max(rows // settings.grid_coarsen, 1))


def block_mean(a: np.ndarray, nrows: int, ncols: int) -> np.ndarray:
    """NaN-aware mean of `a` over an nrows x ncols set of blocks covering the whole array.
    A block with no valid cell stays NaN."""
    if nrows > a.shape[0] or ncols > a.shape[1]:
        raise ValueError(f"cannot resample {a.shape} to a finer grid ({nrows}, {ncols})")
    r = np.linspace(0, a.shape[0], nrows + 1).astype(int)[:-1]
    c = np.linspace(0, a.shape[1], ncols + 1).astype(int)[:-1]
    ok = ~np.isnan(a)
    total = np.add.reduceat(np.add.reduceat(np.where(ok, a, 0.0), r, axis=0), c, axis=1)
    count = np.add.reduceat(np.add.reduceat(ok.astype(np.float64), r, axis=0), c, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / count
    out[count == 0] = np.nan
    return out


def ingest_relief(settings, grid: GridSpec | None = None) -> ReliefData:
    grid = grid or grid_for(settings)
    path = dem_path(settings)
    if not path.is_file():
        raise LayerDataError("relief", f"Elevation grid not found: {path}. {FIX}")
    try:
        raw = tifffile.imread(path).astype("float64")
    except Exception as ex:  # noqa: BLE001
        raise LayerDataError("relief", f"Elevation grid unreadable: {ex}. {FIX} (add --force)") from ex
    if raw.ndim != 2:
        raise LayerDataError("relief", f"Elevation grid must be 2-D, got shape {raw.shape}")
    raw[raw <= NODATA_BELOW] = np.nan
    elev = block_mean(raw, grid.nrows, grid.ncols).astype(np.float32)
    valid = ~np.isnan(elev)
    data = ReliefData(
        grid=grid, elev_m=elev, valid=valid, slope_deg=slope_deg(elev, grid), roughness_m=roughness_m(elev),
        source_files=(f"{path.relative_to(settings.raw_dir).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}",),
    )
    validate_relief(data)
    return data
