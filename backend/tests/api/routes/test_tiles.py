def test_tiles(client):
    r = client.get("/api/tiles/ctx_coprates/5/2/3")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/tiles/hillshade_color/5/2/3").headers["content-type"] == "image/jpeg"
    assert client.get("/api/tiles/ctx_coprates/5/2/99").status_code == 404
    assert client.get("/api/tiles/nope/5/2/3").status_code == 404
    assert client.get("/api/tiles/..%2F..%2Fetc/5/2/3").status_code == 404
    assert client.get("/api/tiles/ctx_coprates/5/2/abc").status_code == 422


def test_tiles_without_data(empty_client):
    assert empty_client.get("/api/tiles/ctx_coprates/5/2/3").status_code == 404
