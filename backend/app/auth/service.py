"""User registration, login and profile updates."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import dummy_hash, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import UserCreate, UserUpdate


class EmailAlreadyRegistered(Exception):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def register_user(db: Session, data: UserCreate) -> User:
    user = User(
        email=normalize_email(data.email),
        hashed_password=hash_password(data.password),
        body_mass_kg=data.body_mass_kg,
        birth_year=data.birth_year,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:  # the unique index also catches two concurrent sign-ups
        db.rollback()
        raise EmailAlreadyRegistered(user.email) from error
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """None for an unknown email and for a wrong password alike."""
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(password, dummy_hash())
        return None
    return user if verify_password(password, user.hashed_password) else None


def update_user(db: Session, user: User, data: UserUpdate) -> User:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
