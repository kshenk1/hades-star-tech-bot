"""
SQLAlchemy models for the Hades Star Discord bot.

Schema:
    Guild        - one row per Discord server the bot is in
    Player       - one row per (guild, discord user) — a member's profile
    ModType      - static reference table, seeded from data/mods_seed.json
    ShipType     - static reference table, seeded from data/ships_seed.json
    PlayerMod    - a player's level in a given mod (many-to-many w/ level)
    PlayerShip   - a player's level in a given ship design

Everything player-owned is scoped by guild_id so the same Discord user
can have independent stats in different servers (e.g. alts, different corps).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Guild(Base):
    __tablename__ = "guilds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # discord guild id
    name: Mapped[str] = mapped_column(String(200))
    # role name/id allowed to edit OTHER people's stats; None = self-service only
    officer_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    players: Mapped[list["Player"]] = relationship(back_populates="guild", cascade="all, delete-orphan")


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("guild_id", "discord_user_id", name="uq_player_guild_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id"))
    discord_user_id: Mapped[int] = mapped_column(BigInteger)
    display_name: Mapped[str] = mapped_column(String(100))
    corp_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(60), nullable=True)  # IANA name, e.g. "America/New_York"
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    guild: Mapped["Guild"] = relationship(back_populates="players")
    mods: Mapped[list["PlayerMod"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    ships: Mapped[list["PlayerShip"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class ModType(Base):
    """Static reference data — seeded once from data/mods_seed.json, not user-editable."""

    __tablename__ = "mod_types"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)  # e.g. "TransportCapacity"
    name: Mapped[str] = mapped_column(String(60))
    slot_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # Trade / Mining / Support / etc.
    max_level: Mapped[int] = mapped_column(Integer, default=15)
    min_level: Mapped[int] = mapped_column(Integer, default=1)  # some mods don't start at 1, e.g. Motion Shield starts at 6

    aliases: Mapped[list["ModAlias"]] = relationship(back_populates="mod_type", cascade="all, delete-orphan")


class ModAlias(Base):
    """Hand-curated shorthand names for a mod (e.g. 'cargobay' -> TransportCapacity).

    Seeded from the "aliases" array in data/mods_seed.json. Curated by the bot
    owner only — seed.py wipes and rebuilds this table on every run, so these
    are NOT meant to be added by end users at runtime.
    """

    __tablename__ = "mod_aliases"
    __table_args__ = (UniqueConstraint("mod_key", "alias", name="uq_mod_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mod_key: Mapped[str] = mapped_column(String(60), ForeignKey("mod_types.key"))
    alias: Mapped[str] = mapped_column(String(60), index=True)

    mod_type: Mapped["ModType"] = relationship(back_populates="aliases")


class ShipType(Base):
    """Static reference data — seeded once from data/ships_seed.json, not user-editable."""

    __tablename__ = "ship_types"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)  # e.g. "Battleship"
    name: Mapped[str] = mapped_column(String(60))
    is_combat_ship: Mapped[bool] = mapped_column(Boolean, default=False)
    max_level: Mapped[int] = mapped_column(Integer, default=1)


class PlayerMod(Base):
    __tablename__ = "player_mods"
    __table_args__ = (UniqueConstraint("player_id", "mod_key", name="uq_player_mod"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"))
    mod_key: Mapped[str] = mapped_column(String(60), ForeignKey("mod_types.key"))
    level: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    player: Mapped["Player"] = relationship(back_populates="mods")
    mod_type: Mapped["ModType"] = relationship()


class PlayerShip(Base):
    __tablename__ = "player_ships"
    __table_args__ = (UniqueConstraint("player_id", "ship_key", name="uq_player_ship"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"))
    ship_key: Mapped[str] = mapped_column(String(60), ForeignKey("ship_types.key"))
    level: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    player: Mapped["Player"] = relationship(back_populates="ships")
    ship_type: Mapped["ShipType"] = relationship()


class WarRoster(Base):
    """A White Star Battle roster — the 10 players locked in for one battle, and when it ran.

    Identified by its Discord role (role_id) rather than just guild_id, since multiple
    battles can run concurrently in the same guild under different roles — but the same
    player can't be a participant in more than one ACTIVE (ended_at IS NULL) roster at once.
    """

    __tablename__ = "war_rosters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.id"))
    role_id: Mapped[int] = mapped_column(BigInteger)
    role_name: Mapped[str] = mapped_column(String(100))  # snapshot at creation, in case the role is later renamed/deleted
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)  # NULL while in progress
    opponent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    relics_us: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relics_them: Mapped[int | None] = mapped_column(Integer, nullable=True)

    participants: Mapped[list["WarRosterParticipant"]] = relationship(back_populates="roster", cascade="all, delete-orphan")


class WarRosterParticipant(Base):
    __tablename__ = "war_roster_participants"
    __table_args__ = (UniqueConstraint("roster_id", "player_id", name="uq_roster_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roster_id: Mapped[int] = mapped_column(Integer, ForeignKey("war_rosters.id"))
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"))

    roster: Mapped["WarRoster"] = relationship(back_populates="participants")
    player: Mapped["Player"] = relationship()
