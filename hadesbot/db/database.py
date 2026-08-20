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


COLUMNS_ADDED_AFTER_LAUNCH = [
    # (table, column, ALTER TABLE ... ADD COLUMN clause)
    ("mod_types", "min_level", "ALTER TABLE mod_types ADD COLUMN min_level INTEGER DEFAULT 1"),
    ("players", "timezone", "ALTER TABLE players ADD COLUMN timezone VARCHAR(60)"),
    ("war_rosters", "role_id", "ALTER TABLE war_rosters ADD COLUMN role_id BIGINT"),
    ("war_rosters", "role_name", "ALTER TABLE war_rosters ADD COLUMN role_name VARCHAR(100)"),
    ("war_rosters", "opponent", "ALTER TABLE war_rosters ADD COLUMN opponent VARCHAR(200)"),
    ("war_rosters", "relics_us", "ALTER TABLE war_rosters ADD COLUMN relics_us INTEGER"),
    ("war_rosters", "relics_them", "ALTER TABLE war_rosters ADD COLUMN relics_them INTEGER"),
]


def _add_missing_columns():
    """create_all() only adds new tables, not new columns on existing ones —
    patch in columns added after a table already existed on disk."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    for table, column, alter_sql in COLUMNS_ADDED_AFTER_LAUNCH:
        if table not in table_names:
            continue
        existing_columns = {col["name"] for col in inspector.get_columns(table)}
        if column not in existing_columns:
            with engine.begin() as conn:
                conn.execute(text(alter_sql))


def get_session():
    return SessionLocal()
