"""Uses empty_client: a fresh data folder per test, so every test starts with an empty database."""
from datetime import date

NEW_USER = {"email": "Astro@Example.com", "password": "correct-horse", "body_mass_kg": 72.0, "birth_year": 1990}


def login(client, email="astro@example.com", password="correct-horse"):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_register_returns_user_without_password(empty_client):
    r = empty_client.post("/api/auth/register", json=NEW_USER)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "email", "body_mass_kg", "birth_year", "created_at"}
    assert body["email"] == "astro@example.com"


def test_register_duplicate_email_is_409(empty_client):
    empty_client.post("/api/auth/register", json=NEW_USER)
    r = empty_client.post("/api/auth/register", json={**NEW_USER, "email": "astro@example.com"})
    assert r.status_code == 409


def test_register_validates_mass_and_birth_year(empty_client):
    assert empty_client.post("/api/auth/register", json={**NEW_USER, "body_mass_kg": 5}).status_code == 422
    assert empty_client.post("/api/auth/register", json={**NEW_USER, "birth_year": date.today().year + 1}).status_code == 422


def test_login_returns_bearer_token(empty_client):
    empty_client.post("/api/auth/register", json=NEW_USER)
    r = login(empty_client)
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer" and r.json()["access_token"]


def test_wrong_password_and_unknown_email_get_the_same_401(empty_client):
    empty_client.post("/api/auth/register", json=NEW_USER)
    wrong_password = login(empty_client, password="wrong-horse")
    unknown_email = login(empty_client, email="nobody@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
