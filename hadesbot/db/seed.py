"""
Loads static mod/ship reference data (data/mods_seed.json, data/ships_seed.json)
into the mod_types / ship_types tables. Safe to re-run — upserts by key.

Mod aliases (shorthand names like "cargobay" for "Cargo Bay Extension") are
hand-curated directly in data/mods_seed.json under each mod's "aliases" array,
e.g.:
    {"key": "TransportCapacity", "name": "Cargo Bay Extension", "aliases": ["cargobay", "cargo-bay"]}
This table is rebuilt from that file on every run — do not add aliases via
Discord commands or expect them to survive a bot restart if added elsewhere.

Source: parsed from userXinos/HadesSpace (github.com/userXinos/HadesSpace),
an open-source Hades Star data-mining project. That repo pulls modules.csv /
capital_ships.csv from the game's own data tables, so max_level here reflects
each mod/ship's actual highest upgrade tier (length of its upgrade-cost array).

Run standalone with: python -m db.seed
Pass --clear to also delete mod_types/ship_types rows whose key no longer
appears in the seed JSON (e.g. after removing an entry from mods_seed.json).
Rows still referenced by PlayerMod/PlayerShip will raise an IntegrityError
instead of being silently orphaned or cascaded away.
"""
import json
import os
import sys

from db.database import get_session, init_db
from db.models import ModAlias, ModType, ShipType

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def seed(clear: bool = False):
    init_db()
    session = get_session()

    with open(os.path.join(DATA_DIR, "mods_seed.json")) as f:
        mods = json.load(f)
    with open(os.path.join(DATA_DIR, "ships_seed.json")) as f:
        ships = json.load(f)

    if clear:
        mod_keys = {m["key"] for m in mods}
        ship_keys = {s["key"] for s in ships}

        stale_mod_keys = [k for (k,) in session.query(ModType.key).filter(ModType.key.notin_(mod_keys))]
        if stale_mod_keys:
            session.query(ModAlias).filter(ModAlias.mod_key.in_(stale_mod_keys)).delete(synchronize_session=False)
            session.query(ModType).filter(ModType.key.in_(stale_mod_keys)).delete(synchronize_session=False)

        stale_ship_keys = [k for (k,) in session.query(ShipType.key).filter(ShipType.key.notin_(ship_keys))]
        if stale_ship_keys:
            session.query(ShipType).filter(ShipType.key.in_(stale_ship_keys)).delete(synchronize_session=False)

        session.commit()
        if stale_mod_keys or stale_ship_keys:
            print(f"Cleared {len(stale_mod_keys)} stale mod type(s) and {len(stale_ship_keys)} stale ship type(s).")

    for m in mods:
        existing = session.get(ModType, m["key"])
        if existing:
            existing.name = m["name"]
            existing.slot_type = m.get("slot_type")
            existing.max_level = m["max_level"]
            existing.min_level = m.get("min_level", 1)
        else:
            existing = ModType(
                key=m["key"],
                name=m["name"],
                slot_type=m.get("slot_type"),
                max_level=m["max_level"],
                min_level=m.get("min_level", 1),
            )
            session.add(existing)
            session.flush()  # need mod_types row to exist before FK'd aliases

        # Aliases are hand-curated in the seed file (not user-submitted), so it's
        # safe to wipe and rebuild this mod's alias set on every run.
        session.query(ModAlias).filter(ModAlias.mod_key == m["key"]).delete()
        for alias in m.get("aliases", []):
            alias = alias.strip().lower()
            if alias:
                session.add(ModAlias(mod_key=m["key"], alias=alias))

    for s in ships:
        existing = session.get(ShipType, s["key"])
        if existing:
            existing.name = s["name"]
            existing.is_combat_ship = s["is_combat_ship"]
            existing.max_level = s["max_level"]
        else:
            session.add(
                ShipType(
                    key=s["key"],
                    name=s["name"],
                    is_combat_ship=s["is_combat_ship"],
                    max_level=s["max_level"],
                )
            )

    session.commit()
    alias_count = sum(len(m.get("aliases", [])) for m in mods)
    print(f"Seeded {len(mods)} mod types ({alias_count} aliases) and {len(ships)} ship types.")
    session.close()


if __name__ == "__main__":
    seed(clear="--clear" in sys.argv)
