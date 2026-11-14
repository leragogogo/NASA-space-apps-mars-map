from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    MAX_BODY_MASS_KG,
    MIN_BIRTH_YEAR,
    MIN_BODY_MASS_KG,
    Token,
    check_birth_year,
    UserCreate,
    UserUpdate,
)

VALID = {"email": "astro@example.com", "password": "correct-horse", "body_mass_kg": 72.0, "birth_year": date.today().year - 35}


def test_valid_user_create():
    assert UserCreate(**VALID).body_mass_kg == 72.0


@pytest.mark.parametrize("field, value", [
    ("email", "not-an-email"),
    ("body_mass_kg", MIN_BODY_MASS_KG - 0.1),
    ("body_mass_kg", MAX_BODY_MASS_KG + 0.1),
    ("birth_year", date.today().year + 1),  # in the future
    ("birth_year", MIN_BIRTH_YEAR - 1),
])
def test_user_create_rejects_out_of_range(field, value):
    with pytest.raises(ValidationError):
        UserCreate(**{**VALID, field: value})


@pytest.mark.parametrize("field", ["body_mass_kg", "birth_year"])
def test_mass_and_birth_year_are_required(field):
    data = dict(VALID)
    del data[field]
    with pytest.raises(ValidationError):
        UserCreate(**data)


@pytest.mark.parametrize("password", ["a", "x" * 1000])
def test_password_length_is_not_checked(password):
    assert UserCreate(**{**VALID, "password": password}).password == password


def test_user_update_is_partial_and_checks_ranges():
    assert UserUpdate(birth_year=1990).model_dump(exclude_none=True) == {"birth_year": 1990}
    with pytest.raises(ValidationError):
        UserUpdate(body_mass_kg=MAX_BODY_MASS_KG + 1)


def test_birth_year_bounds_are_inclusive():
    this_year = date.today().year
    assert check_birth_year(this_year) == this_year
    assert check_birth_year(MIN_BIRTH_YEAR) == MIN_BIRTH_YEAR
    assert check_birth_year(None) is None
    with pytest.raises(ValueError, match="birth_year"):
        check_birth_year(this_year + 1)


def test_token_type_is_bearer():
    assert Token(access_token="abc").token_type == "bearer"
