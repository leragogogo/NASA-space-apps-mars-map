from tests.api.routes.test_auth import NEW_USER, login


def auth_header(client):
    client.post("/api/auth/register", json=NEW_USER)
    return {"Authorization": f"Bearer {login(client).json()['access_token']}"}


def test_me_requires_token(empty_client):
    assert empty_client.get("/api/users/me").status_code == 401
    r = empty_client.get("/api/users/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_me_returns_current_user(empty_client):
    r = empty_client.get("/api/users/me", headers=auth_header(empty_client))
    assert r.status_code == 200
    assert (r.json()["email"], r.json()["body_mass_kg"], r.json()["birth_year"]) == ("astro@example.com", 72.0, 1990)


def test_patch_me_updates_mass_and_birth_year(empty_client):
    headers = auth_header(empty_client)
    r = empty_client.patch("/api/users/me", json={"body_mass_kg": 80.5}, headers=headers)
    assert r.status_code == 200 and (r.json()["body_mass_kg"], r.json()["birth_year"]) == (80.5, 1990)
    assert empty_client.get("/api/users/me", headers=headers).json()["body_mass_kg"] == 80.5
    assert empty_client.patch("/api/users/me", json={"birth_year": 1800}, headers=headers).status_code == 422
    assert empty_client.patch("/api/users/me", json={"birth_year": 1991}).status_code == 401
