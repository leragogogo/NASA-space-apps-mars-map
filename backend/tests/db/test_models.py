import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import User


def _user(email="a@example.com"):
    return User(email=email, hashed_password="hash", body_mass_kg=70.5, birth_year=1990)


def test_user_round_trip_sets_id_and_created_at(db_session):
    user = _user()
    db_session.add(user)
    db_session.commit()
    stored = db_session.get(User, user.id)
    assert (stored.email, stored.body_mass_kg, stored.birth_year) == ("a@example.com", 70.5, 1990)
    assert stored.created_at is not None


def test_email_is_unique(db_session):
    db_session.add(_user())
    db_session.commit()
    db_session.add(_user())
    with pytest.raises(IntegrityError):
        db_session.commit()
