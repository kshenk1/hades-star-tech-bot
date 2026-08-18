import os

from sqlalchemy import create_engine
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


def get_session():
    return SessionLocal()
