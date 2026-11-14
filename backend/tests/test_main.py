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


def test_auth_routers_are_wired(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {"/api/auth/register", "/api/auth/login", "/api/users/me"} <= paths


def test_app_refuses_to_start_without_jwt_secret(tmp_path):
    import pytest
    from app.core.config import Settings
    from main import create_app
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_app(Settings(data_dir=tmp_path, jwt_secret_key=None))
