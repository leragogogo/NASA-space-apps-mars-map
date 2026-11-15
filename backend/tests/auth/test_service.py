import pytest

from app.auth.service import (
    EmailAlreadyRegistered,
    authenticate,
    get_user_by_email,
    normalize_email,
    register_user,
    update_user,
)
from app.schemas.auth import UserCreate, UserUpdate

NEW_USER = UserCreate(email="Astro@Example.com", password="correct-horse", body_mass_kg=72.0, birth_year=1990)


def test_normalize_email():
    assert normalize_email("  Astro@Example.COM ") == "astro@example.com"


def test_register_stores_lowercased_email_and_hashed_password(db_session):
    user = register_user(db_session, NEW_USER)
    assert user.id is not None and user.email == "astro@example.com"
    assert user.hashed_password != "correct-horse"
    assert (user.body_mass_kg, user.birth_year) == (72.0, 1990)


def test_register_twice_raises_even_with_other_case(db_session):
    register_user(db_session, NEW_USER)
    with pytest.raises(EmailAlreadyRegistered):
        register_user(db_session, NEW_USER.model_copy(update={"email": "ASTRO@example.com"}))
    assert get_user_by_email(db_session, "astro@example.com") is not None  # session still usable


def test_authenticate(db_session):
    user = register_user(db_session, NEW_USER)
    assert authenticate(db_session, "ASTRO@example.com", "correct-horse").id == user.id
    assert authenticate(db_session, "astro@example.com", "wrong-horse") is None
    assert authenticate(db_session, "nobody@example.com", "correct-horse") is None


def test_update_user_changes_only_sent_fields(db_session):
    user = register_user(db_session, NEW_USER)
    update_user(db_session, user, UserUpdate(birth_year=1991))
    assert (user.body_mass_kg, user.birth_year) == (72.0, 1991)
    update_user(db_session, user, UserUpdate(body_mass_kg=80.0))
    assert (user.body_mass_kg, user.birth_year) == (80.0, 1991)
