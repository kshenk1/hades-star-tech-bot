import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from db.models import Base

DB_PATH = os.getenv("DATABASE_URL", "sqlite:///hadesbot.db")

# check_same_thread=False is needed because discord.py callbacks run in
# an event loop, not the thread sqlite3 was opened on. SQLite writes are
# still effectively serialized, which is fine at this scale.
engine = create_engine(
    DB_PATH,
    connect_args={"check_same_thread": False} if DB_PATH.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns():
    """create_all() only adds new tables, not new columns on existing ones —
    patch in columns added after a table already existed on disk."""
    inspector = inspect(engine)
    if "mod_types" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("mod_types")}
    if "min_level" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE mod_types ADD COLUMN min_level INTEGER DEFAULT 1"))


def get_session():
    return SessionLocal()
