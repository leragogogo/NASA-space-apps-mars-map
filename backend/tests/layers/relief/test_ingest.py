import numpy as np
import pytest
import tifffile
from tests.conftest import DEM_SHAPE, FIXTURE_SLOPE_DEG

from app.core.config import Settings
from app.layers.contracts import LayerDataError
from app.layers.relief.ingest import block_mean, grid_for, ingest_relief
from app.layers.validate import validate_relief


def test_block_mean_is_nan_aware():
    a = np.array([[1.0, 3.0, np.nan, np.nan], [5.0, np.nan, np.nan, np.nan]])
    out = block_mean(a, 1, 2)
    assert out[0, 0] == pytest.approx(3.0)  # mean of 1, 3, 5 (NaN ignored)
    assert np.isnan(out[0, 1])              # a block without valid cells stays NaN


def test_block_mean_handles_non_divisible_shapes():
    a = np.arange(35, dtype=float).reshape(5, 7)
    out = block_mean(a, 2, 3)
    assert out.shape == (2, 3) and np.isfinite(out).all()
    assert block_mean(a, 5, 7) == pytest.approx(a)
    with pytest.raises(ValueError):
        block_mean(a, 6, 7)


def test_ingest_matches_contract(fixture_settings):
    d = ingest_relief(fixture_settings)
    validate_relief(d)
    assert d.grid.shape == DEM_SHAPE and d.elev_m.dtype == np.float32 and d.valid.all()
    assert np.allclose(d.slope_deg, FIXTURE_SLOPE_DEG, atol=1e-3)
    assert d.source_files[0].startswith("dem/dem_blend200m_aoi.tif:") and len(d.source_files[0]) > 60


def test_coarsen_shrinks_the_grid_and_keeps_the_plane_slope(fixture_data):
    s = Settings(data_dir=fixture_data, grid_coarsen=2)
    assert grid_for(s).shape == (DEM_SHAPE[0] // 2, DEM_SHAPE[1] // 2)
    d = ingest_relief(s)
    assert d.grid.shape == (3, 4)
    assert np.allclose(d.slope_deg, FIXTURE_SLOPE_DEG, atol=0.5)


def test_nodata_becomes_nan_and_invalid(tmp_path):
    (tmp_path / "raw" / "dem").mkdir(parents=True)
    dem = np.linspace(-3000, -2000, 48, dtype="float32").reshape(6, 8)
    dem[2, 3] = -32767
    tifffile.imwrite(tmp_path / "raw/dem/dem_blend200m_aoi.tif", dem)
    d = ingest_relief(Settings(data_dir=tmp_path, grid_coarsen=1))
    assert np.isnan(d.elev_m[2, 3]) and not d.valid[2, 3] and d.valid.sum() == 47


def test_missing_dem_raises_with_fix(tmp_path):
    with pytest.raises(LayerDataError) as ex:
        ingest_relief(Settings(data_dir=tmp_path))
    assert "--only dem" in ex.value.message and ex.value.layer == "relief"
    settings = Settings(data_dir=tmp_path)
    assert grid_for(settings).shape == (1073 // settings.grid_coarsen, 1200 // settings.grid_coarsen)  # default DEM shape
