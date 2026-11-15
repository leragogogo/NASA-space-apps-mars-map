import pytest

from app.core.resources import EDGE_ATTRS, PROFILES, ProfileId, attr_key, split_attr_key


def test_profiles_and_attrs():
    assert [p.value for p in PROFILES] == ["astronaut", "car"]
    assert EDGE_ATTRS[0] == "cost" and "o2_g" in EDGE_ATTRS


def test_attr_key_roundtrip():
    key = attr_key(ProfileId.ASTRONAUT, "o2_g")
    assert key == "astronaut__o2_g"
    assert split_attr_key(key) == (ProfileId.ASTRONAUT, "o2_g")
    assert attr_key("car", "energy_wh") == "car__energy_wh"


@pytest.mark.parametrize("bad", ["nonsense", ""])
def test_unknown_attr_rejected(bad):
    with pytest.raises(ValueError):
        attr_key("car", bad)


def test_unknown_profile_and_bad_key_rejected():
    with pytest.raises(ValueError):
        attr_key("hovercraft", "cost")
    with pytest.raises(ValueError):
        split_attr_key("astronaut_cost")
