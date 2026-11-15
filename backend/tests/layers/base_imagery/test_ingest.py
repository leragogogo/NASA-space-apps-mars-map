import pytest

from app.core.config import Settings
from app.layers.base_imagery.ingest import ingest_imagery
from app.layers.contracts import LayerDataError


def test_catalog_lists_base_sources_by_folder_label(fixture_settings):
    cat = ingest_imagery(fixture_settings)
    assert [l.id for l in cat.layers] == ["Coprates_EMelas_Chasm_CTX_BlockAdj_dd", "HiRISE_Global"]
    ctx, hirise = cat.layers
    assert (ctx.tile_size, ctx.ext, ctx.min_zoom, ctx.max_zoom) == (256, "png", 5, 6)
    assert hirise.tile_size == 512 and hirise.role == "zoom-in detail"
    assert ctx.bounds == (-71.8, -13.4, -68.0, -10.0)


def test_tile_path_exists_or_none(fixture_settings):
    cat = ingest_imagery(fixture_settings)
    assert cat.tile_path("Coprates_EMelas_Chasm_CTX_BlockAdj_dd", 5, 2, 3).is_file()
    assert cat.tile_path("Coprates_EMelas_Chasm_CTX_BlockAdj_dd", 5, 0, 0) is None  # not downloaded -> 404


def test_missing_tiles_raise_with_fix(tmp_path):
    with pytest.raises(LayerDataError) as ex:
        ingest_imagery(Settings(data_dir=tmp_path))
    assert "download_data.py --only tiles" in ex.value.message and ex.value.layer == "base_imagery"
