from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


def make_engine(url):
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False, "timeout": 15}
                           if parsed.get_backend_name() == "sqlite" else {})
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def sqlite_settings(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=15000")
            connection.execute("PRAGMA journal_mode=WAL")
    return engine


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)
