import io

from PIL import Image

from tests.conftest import DEM_SHAPE


# ---- Layer 1
def test_layer_one(client):
    d = client.get("/api/get-layer-one").json()
    assert d["default_source"] == "ctx_coprates"
    assert [s["id"] for s in d["sources"]] == ["ctx_coprates", "hirise"]


# ---- Layer 2
def test_layer_two(client):
    d = client.get("/api/get-layer-two").json()
    assert len(d["slope_classes"]) == 5 and d["overlay"]["url"] == "/api/get-layer-two/walkability.png"
    assert [h["id"] for h in d["hillshade_sources"]] == ["hillshade_color"]


def test_walkability_png(client):
    r = client.get("/api/get-layer-two/walkability.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size == (DEM_SHAPE[1], DEM_SHAPE[0])


def test_point(client):
    p = client.get("/api/get-layer-two/point", params={"lon": -70.0, "lat": -12.0}).json()
    assert p["slope_class"] == "walkable" and p["approximate"] is True
    out = client.get("/api/get-layer-two/point", params={"lon": -60.0, "lat": -12.0})
    assert out.status_code == 404 and "outside" in out.json()["detail"]
    assert client.get("/api/get-layer-two/point", params={"lon": -70.0}).status_code == 422


# ---- Layer 3
def test_layer_three(client):
    d = client.get("/api/get-layer-three").json()
    assert d["type"] == "FeatureCollection" and len(d["features"]) == 7
    assert d["overlays"][0]["id"] == "crism_sulfate"
    only = client.get("/api/get-layer-three", params={"category": "mineral, water_activity"}).json()
    assert {f["properties"]["category"] for f in only["features"]} == {"mineral", "water_activity"}
    bad = client.get("/api/get-layer-three", params={"category": "mineral,unicorns"})
    assert bad.status_code == 422 and "unicorns" in bad.json()["detail"]


# ---- Layer 4
def test_layer_four(client):
    d = client.get("/api/get-layer-four", params={"season": "winter"}).json()
    assert d["season"] == "winter" and len(d["features"]) == 3 and d["caveat"] == "Fixture caveat."
    styles = sorted(f["properties"]["display_style"] for f in d["features"])
    assert styles == ["grey", "hatched", "solid"]
    assert client.get("/api/get-layer-four").status_code == 422
    assert client.get("/api/get-layer-four", params={"season": "monsoon"}).status_code == 422


# ---- Missing data: every layer 503, server still up
def test_missing_data_gives_503(empty_client):
    expected_fix = {
        "/api/get-layer-one": "download_data.py --only tiles",
        "/api/get-layer-two": "download_data.py --only dem",
        "/api/get-layer-two/walkability.png": "download_data.py --only dem",
        "/api/get-layer-two/point?lon=-70&lat=-12": "download_data.py --only dem",
        "/api/get-layer-three": "download_data.py --only pois",
        "/api/get-layer-four?season=winter": "build_weather/build_weather.py",
    }
    for url, fix in expected_fix.items():
        r = empty_client.get(url)
        assert r.status_code == 503, url
        assert fix in r.json()["fix"] and r.json()["detail"], url
