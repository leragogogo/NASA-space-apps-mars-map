from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.security import (
    create_access_token,
    decode_access_token,
    dummy_hash,
    hash_password,
    verify_password,
)
from app.core.config import Settings
from tests.conftest import TEST_JWT_SECRET

SETTINGS = Settings(jwt_secret_key=TEST_JWT_SECRET)


def test_password_hash_round_trip():
    hashed = hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong-horse", hashed)


def test_dummy_hash_is_cached_and_matches_no_normal_password():
    assert dummy_hash() is dummy_hash()
    assert not verify_password("correct-horse", dummy_hash())


def test_token_round_trip():
    assert decode_access_token(create_access_token(42, SETTINGS), SETTINGS) == 42


def test_token_expires():
    issued = datetime.now(timezone.utc) - timedelta(minutes=SETTINGS.access_token_expire_minutes + 1)
    token = create_access_token(42, SETTINGS, now=issued)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, SETTINGS)


def test_token_signed_with_another_key_is_rejected():
    other = Settings(jwt_secret_key="another-secret-key-that-is-32-bytes-long")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(create_access_token(42, other), SETTINGS)


@pytest.mark.parametrize("claims", [
    {"exp": datetime.now(timezone.utc) + timedelta(minutes=5)},                 # no sub
    {"sub": "42"},                                                               # no exp
    {"sub": "abc", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},  # sub is not an id
])
def test_malformed_claims_are_rejected(claims):
    token = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, SETTINGS)


def test_garbage_token_is_rejected():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not.a.token", SETTINGS)
