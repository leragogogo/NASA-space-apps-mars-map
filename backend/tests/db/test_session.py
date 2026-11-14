from sqlalchemy import inspect

from app.db.session import init_db, make_engine


def test_make_engine_creates_missing_parent_folder(tmp_path):
    db_file = tmp_path / "not" / "yet" / "app.db"
    engine = make_engine(f"sqlite:///{db_file}")
    init_db(engine)
    assert db_file.is_file()
    engine.dispose()


def test_init_db_creates_users_table(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    session_factory = init_db(engine)
    assert "users" in inspect(engine).get_table_names()
    with session_factory() as session:
        assert session.bind is engine
    engine.dispose()


def test_init_db_is_idempotent(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'app.db'}")
    init_db(engine)
    init_db(engine)
    engine.dispose()


def test_in_memory_url_is_accepted():
    engine = make_engine("sqlite://")
    init_db(engine)
    assert "users" in inspect(engine).get_table_names()
    engine.dispose()
