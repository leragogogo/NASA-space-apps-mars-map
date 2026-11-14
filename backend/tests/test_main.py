def test_hello_still_works(client):
    assert client.get("/api/hello").json() == {"message": "Hello from FastAPI"}


def test_routers_are_wired(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {"/api/get-layer-one", "/api/get-layer-two", "/api/get-layer-three", "/api/get-layer-four",
            "/api/tiles/{source}/{z}/{row}/{col}"} <= paths


def test_unavailable_layer_handler_returns_503(empty_client):
    r = empty_client.get("/api/get-layer-one")
    assert r.status_code == 503 and set(r.json()) == {"detail", "fix"}
    assert empty_client.get("/api/hello").status_code == 200
