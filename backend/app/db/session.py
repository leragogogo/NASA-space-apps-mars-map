"""Engine and per-request sessions. One engine per app, kept on app.state (no global engine)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    connect_args = {}
    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False  # FastAPI runs sync endpoints in a thread pool
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)  # data/ may not exist yet
    return create_engine(url, connect_args=connect_args)


def init_db(engine: Engine) -> sessionmaker[Session]:
    """Create missing tables and return the session factory."""
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
