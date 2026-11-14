"""API models for /api/auth/* and /api/users/me."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# TODO: move to a shared constants module (e.g. app/core/constants.py).
MIN_BODY_MASS_KG = 30.0
# TODO: move to a shared constants module (e.g. app/core/constants.py).
MAX_BODY_MASS_KG = 250.0
# TODO: move to a shared constants module (e.g. app/core/constants.py).
MIN_BIRTH_YEAR = 1900


def check_birth_year(birth_year: int | None) -> int | None:
    """A real year: from MIN_BIRTH_YEAR up to the current year (no future years)."""
    if birth_year is None:
        return None
    this_year = date.today().year
    if not MIN_BIRTH_YEAR <= birth_year <= this_year:
        raise ValueError(f"birth_year must be between {MIN_BIRTH_YEAR} and {this_year}")
    return birth_year


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    body_mass_kg: float = Field(ge=MIN_BODY_MASS_KG, le=MAX_BODY_MASS_KG)
    birth_year: int

    _check_birth_year = field_validator("birth_year")(check_birth_year)


class UserUpdate(BaseModel):
    """Only the fields that are sent are changed."""

    body_mass_kg: float | None = Field(default=None, ge=MIN_BODY_MASS_KG, le=MAX_BODY_MASS_KG)
    birth_year: int | None = None

    _check_birth_year = field_validator("birth_year")(check_birth_year)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    body_mass_kg: float
    birth_year: int
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
