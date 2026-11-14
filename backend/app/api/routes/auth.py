from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.dependencies import get_settings
from app.auth.security import create_access_token
from app.auth.service import EmailAlreadyRegistered, authenticate, register_user
from app.core.config import Settings
from app.db.session import get_db
from app.schemas.auth import Token, UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    try:
        return register_user(db, data)
    except EmailAlreadyRegistered:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """OAuth2 password form: the email goes in the `username` field (this makes Swagger's Authorize work)."""
    user = authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id, settings))
