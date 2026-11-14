import pytest
from fastapi import HTTPException

from app.auth.dependencies import get_current_user
from app.auth.security import create_access_token
from app.auth.service import register_user
from app.core.config import Settings
from app.schemas.auth import UserCreate
from tests.conftest import TEST_JWT_SECRET

SETTINGS = Settings(jwt_secret_key=TEST_JWT_SECRET)
NEW_USER = UserCreate(email="astro@example.com", password="correct-horse", body_mass_kg=72.0, birth_year=1990)


def test_valid_token_returns_user(db_session):
    user = register_user(db_session, NEW_USER)
    assert get_current_user(create_access_token(user.id, SETTINGS), db_session, SETTINGS).id == user.id


@pytest.mark.parametrize("token", ["garbage", None])
def test_invalid_token_or_unknown_user_is_401(db_session, token):
    token = token or create_access_token(999, SETTINGS)  # None: valid token for a user that does not exist
    with pytest.raises(HTTPException) as error:
        get_current_user(token, db_session, SETTINGS)
    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}
