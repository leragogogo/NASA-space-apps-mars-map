import pytest

from weather.config import SEASON_NAMES
from weather.mdad import hits_box, inside, load_mdad, season_of
from weather.tests.helpers import RAW_COLUMNS, raw_row, storms, write_mdad


def test_season_boundaries():
    assert season_of(0) == SEASON_NAMES[0] and season_of(89.9) == SEASON_NAMES[0]
    assert season_of(90) == SEASON_NAMES[1] and season_of(180) == SEASON_NAMES[2]
    assert season_of(270) == SEASON_NAMES[3] and season_of(359.9) == SEASON_NAMES[3]
    assert season_of(360) == SEASON_NAMES[3]  # falls back to the last season


def test_load_mdad_adds_derived_columns(tmp_path):
    p = tmp_path / "MDAD_original"
    write_mdad(p, [raw_row(member="B01_001", ls=100.0, lat=-12.0, lat_max=-2.0, lat_min=-22.0, area=2.0e6)])
    d = load_mdad(p)
    r = d.iloc[0]
    assert r.storm_id == "B01_B01_001" and r.season == SEASON_NAMES[1]
    assert r.lat_c == pytest.approx(-12.0)
    assert r.semi_lat_deg == pytest.approx(10 * 1.0 * 0 + r.semi_lat_deg) and r.semi_lat_deg > 0
    assert r.semi_lon_deg > 0


def test_load_mdad_strips_padded_text(tmp_path):
    p = tmp_path / "m"
    write_mdad(p, [raw_row(sub="  B02 ", member=" B02_007 ", missing=" yes ")])
    d = load_mdad(p)
    assert d.iloc[0].subphase == "B02" and d.iloc[0].missing == "yes" and d.iloc[0].storm_id == "B02_B02_007"


def test_load_mdad_rejects_missing_columns(tmp_path):
    p = tmp_path / "m"
    p.write_text(",".join(RAW_COLUMNS[:5]) + "\n1,2,3,4,5\n")
    with pytest.raises(ValueError, match="missing columns"):
        load_mdad(p)


def test_inside_wraps_longitude_at_180():
    d = storms([(28, 100.0, 179.0, 0.0, "a", "no")])
    assert inside(d, -179.0, 0.0).iloc[0]  # 2 deg away across the antimeridian
    assert not inside(d, 0.0, 0.0).iloc[0]
    assert not inside(d, 179.0, 15.0).iloc[0]  # beyond the 10 deg N-S semi-axis


def test_hits_box_counts_covered_fraction():
    d = storms([(28, 100.0, -70.0, -12.0, "a", "no"), (28, 100.0, 100.0, 40.0, "b", "no")])
    h = hits_box(d, (-71.8, -13.4, -68.0, -10.0))
    assert list(h.storm_id) == ["a"] and h.aoi_cover_frac.iloc[0] == 1.0
