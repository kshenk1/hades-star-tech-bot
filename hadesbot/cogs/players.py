from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import or_, select

from db.database import get_session
from db.models import Guild, ModAlias, ModType, Player, PlayerMod, PlayerShip, ShipType


SLOT_TYPE_COLORS = {
    "Mining": discord.Color.purple(),
    "Transport": discord.Color.gold(),
    "Weapon": discord.Color.red(),
    "Shield": discord.Color.from_rgb(0, 255, 255),
    "Drone": discord.Color.orange(),
    "Combat": discord.Color.green(),
}
SLOT_TYPE_ORDER = ["Transport", "Mining", "Weapon", "Shield", "Combat", "Drone"]

SHIP_COLORS = {
    "Transport": discord.Color.gold(),
    "Miner": discord.Color.purple(),
    "Battleship": discord.Color.red(),
}

def get_or_create_player(session, guild: discord.Guild, member: discord.Member) -> Player:
    # ensure guild row exists (FK requirement)
    g = session.get(Guild, guild.id)
    if not g:
        g = Guild(id=guild.id, name=guild.name)
        session.add(g)
        session.flush()

    stmt = select(Player).where(Player.guild_id == guild.id, Player.discord_user_id == member.id)
    player = session.execute(stmt).scalar_one_or_none()
    if not player:
        player = Player(guild_id=guild.id, discord_user_id=member.id, display_name=member.display_name)
        session.add(player)
        session.flush()
    return player

def resolve_mod(session, find_mod: str) -> ModType | None:
    """Look up a ModType by exact key, exact display name, or exact alias (case-insensitive)."""
    find_mod = find_mod.strip()
    if not find_mod:
        return None
    # exact key match first (fastest, and avoids ambiguity)
    mt = session.get(ModType, find_mod)
    if mt:
        return mt
    stmt = (
        select(ModType)
        .outerjoin(ModAlias, ModAlias.mod_key == ModType.key)
        .where(or_(ModType.name.ilike(find_mod), ModAlias.alias.ilike(find_mod)))
        .distinct()
    )
    return session.execute(stmt).scalars().first()

class Players(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- autocomplete helpers ----------

    async def mod_autocomplete(self, interaction: discord.Interaction, current: str):
        session = get_session()
        try:
            # match against the display name OR any hand-curated alias (e.g. "cargobay" -> Cargo Bay Extension)
            stmt = (
                select(ModType)
                .outerjoin(ModAlias, ModAlias.mod_key == ModType.key)
                .where(or_(ModType.name.ilike(f"%{current}%"), ModAlias.alias.ilike(f"%{current}%")))
                .distinct()
                .order_by(ModType.name)
                .limit(25)
            )
            results = session.execute(stmt).scalars().all()
            return [app_commands.Choice(name=m.name, value=m.key) for m in results]
        finally:
            session.close()

    async def mod_type_autocomplete(self, interaction: discord.Interaction, current: str):
        session = get_session()
        try:
            stmt = (
                select(ModType.slot_type)
                .where(ModType.slot_type.ilike(f"%{current}%"))
                .distinct()
                .order_by(ModType.slot_type)
            )
            results = session.execute(stmt).scalars().all()
            return [app_commands.Choice(name=s, value=s) for s in results if s]
        finally:
            session.close()

    async def ship_autocomplete(self, interaction: discord.Interaction, current: str):
        session = get_session()
        try:
            stmt = select(ShipType).where(ShipType.name.ilike(f"%{current}%")).order_by(ShipType.name).limit(25)
            results = session.execute(stmt).scalars().all()
            return [app_commands.Choice(name=s.name, value=s.key) for s in results]
        finally:
            session.close()

    async def timezone_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        matches = sorted(z for z in available_timezones() if current in z.lower())
        return [app_commands.Choice(name=z, value=z) for z in matches[:25]]

    # ---------- mods ----------
    @app_commands.command(name="listmods", description="List all modules and their aliases for a module type")
    @app_commands.autocomplete(mod_type=mod_type_autocomplete)
    async def listmods(self, interaction: discord.Interaction, mod_type: str):
        session = get_session()
        try:
            stmt = select(ModType).where(ModType.slot_type == mod_type).order_by(ModType.name)
            mod_types = session.execute(stmt).scalars().all()
            if not mod_types:
                await interaction.response.send_message("Unknown mod type. Pick one from the autocomplete list.", ephemeral=True)
                return

            lines = []
            for mt in mod_types:
                aliases = [ma.alias for ma in mt.aliases]
                levels = f"levels: {mt.min_level}–{mt.max_level}" if mt.min_level > 1 else f"max level: {mt.max_level}"
                line = f"**{mt.name}** (key: {mt.key}, {levels})"
                if aliases:
                    line += f" — Aliases: {', '.join(aliases)}"
                lines.append(line)

            color = SLOT_TYPE_COLORS.get(mod_type, discord.Color.blurple())
            embed = discord.Embed(title=f"Modules: {mod_type}", description="\n".join(lines), color=color)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="mods", description="List all mods you've set and their levels")
    async def mods(self, interaction: discord.Interaction):
        session = get_session()
        try:
            player = get_or_create_player(session, interaction.guild, interaction.user)
            stmt = (
                select(PlayerMod)
                .join(ModType, PlayerMod.mod_key == ModType.key)
                .where(PlayerMod.player_id == player.id)
                .order_by(ModType.name)
            )
            mods = session.execute(stmt).scalars().all()
            lines = [f"{pm.mod_type.name}: level {pm.level}" for pm in mods]
            embed = discord.Embed(title="All Mods", description="\n".join(lines), color=discord.Color.blurple())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="getmod", description="Get your level for a mod")
    @app_commands.autocomplete(mod=mod_autocomplete)
    async def getmod(self, interaction: discord.Interaction, mod: str):
        session = get_session()
        try:
            mod_type = session.get(ModType, mod)
            if not mod_type:
                await interaction.response.send_message("Unknown mod. Pick one from the autocomplete list.", ephemeral=True)
                return

            player = get_or_create_player(session, interaction.guild, interaction.user)
            stmt = select(PlayerMod).where(PlayerMod.player_id == player.id, PlayerMod.mod_key == mod)
            pm = session.execute(stmt).scalar_one_or_none()
            if pm:
                await interaction.response.send_message(f"Your **{mod_type.name}** is level **{pm.level}**.", ephemeral=True)
            else:
                await interaction.response.send_message(f"You haven't set a level for **{mod_type.name}** yet.", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="setmod", description="Set your level for a mod")
    @app_commands.autocomplete(mod=mod_autocomplete)
    async def setmod(self, interaction: discord.Interaction, mod: str, level: int):
        session = get_session()
        try:
            mod_type = session.get(ModType, mod)
            if not mod_type:
                await interaction.response.send_message("Unknown mod. Pick one from the autocomplete list.", ephemeral=True)
                return
            if not (mod_type.min_level <= level <= mod_type.max_level):
                await interaction.response.send_message(
                    f"{mod_type.name} only goes from level {mod_type.min_level} to {mod_type.max_level}.", ephemeral=True
                )
                return

            player = get_or_create_player(session, interaction.guild, interaction.user)
            stmt = select(PlayerMod).where(PlayerMod.player_id == player.id, PlayerMod.mod_key == mod)
            pm = session.execute(stmt).scalar_one_or_none()
            if pm:
                pm.level = level
            else:
                session.add(PlayerMod(player_id=player.id, mod_key=mod, level=level))
            session.commit()
            await interaction.response.send_message(f"Set **{mod_type.name}** to level **{level}**.", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="setmods", description="Set several mods at once, each to its own level. Format: name:level, name:level, ...",)
    @app_commands.describe(mods='e.g. "mining-boost:8, massbatt:10, crunch:12, ship-comp:5" (names or aliases, comma-separated)')
    async def setmods(self, interaction: discord.Interaction, mods: str):
        session = get_session()
        try:
            entries = [e.strip() for e in mods.split(",") if e.strip()]
            if not entries:
                await interaction.response.send_message(
                    'Give me a comma-separated list like "mining-boost:8, crunch:12".', ephemeral=True
                )
                return

            player = get_or_create_player(session, interaction.guild, interaction.user)

            updated, errors = [], []
            for entry in entries:
                # split on the LAST colon so mod names containing ":" (none currently do, but future-proof) still work
                if ":" not in entry:
                    errors.append(f'"{entry}" (expected name:level)')
                    continue
                name_part, _, level_part = entry.rpartition(":")
                name_part = name_part.strip()
                level_part = level_part.strip()

                if not level_part.isdigit():
                    errors.append(f'"{entry}" (level must be a number)')
                    continue
                level = int(level_part)

                mod_type = resolve_mod(session, name_part)
                if not mod_type:
                    errors.append(f'"{name_part}" (no matching mod)')
                    continue
                if not (mod_type.min_level <= level <= mod_type.max_level):
                    errors.append(f"{mod_type.name} (level must be {mod_type.min_level}-{mod_type.max_level})")
                    continue

                stmt = select(PlayerMod).where(PlayerMod.player_id == player.id, PlayerMod.mod_key == mod_type.key)
                pm = session.execute(stmt).scalar_one_or_none()
                if pm:
                    pm.level = level
                else:
                    session.add(PlayerMod(player_id=player.id, mod_key=mod_type.key, level=level))
                updated.append(f"{mod_type.name}: {level}")

            session.commit()

            embeds = []
            if updated:
                embeds.append(discord.Embed(title=f"✅ Updated ({len(updated)})", description="\n".join(updated), color=discord.Color.green()))
            if errors:
                embeds.append(discord.Embed(title=f"⚠️ Skipped ({len(errors)})", description="\n".join(errors), color=discord.Color.red()))

            if embeds:
                await interaction.response.send_message(embeds=embeds, ephemeral=True)
            else:
                await interaction.response.send_message("Nothing to update.", ephemeral=True)
        finally:
            session.close()

    # ---------- ships ----------
    @app_commands.command(name="ships", description="Show your ship designs and levels")
    async def ships(self, interaction: discord.Interaction):
        session = get_session()
        try:
            player = get_or_create_player(session, interaction.guild, interaction.user)
            stmt = (
                select(PlayerShip)
                .join(ShipType, PlayerShip.ship_key == ShipType.key)
                .where(PlayerShip.player_id == player.id)
                .order_by(ShipType.name)
            )
            player_ships = session.execute(stmt).scalars().all()
            if not player_ships:
                await interaction.response.send_message("You haven't set any ship designs yet.", ephemeral=True)
                return
            embeds = [
                discord.Embed(
                    title=ps.ship_type.name,
                    description=f"Level {ps.level}",
                    color=SHIP_COLORS.get(ps.ship_type.key, discord.Color.blurple()),
                )
                for ps in player_ships
            ]
            await interaction.response.send_message(embeds=embeds, ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="getship", description="Get your level for a ship design")
    @app_commands.autocomplete(ship=ship_autocomplete)
    async def getship(self, interaction: discord.Interaction, ship: str):
        session = get_session()
        try:
            player = get_or_create_player(session, interaction.guild, interaction.user)
            stmt = select(PlayerShip).where(PlayerShip.player_id == player.id, PlayerShip.ship_key == ship)
            ps = session.execute(stmt).scalar_one_or_none()
            if ps:
                await interaction.response.send_message(f"Your level for {ps.ship_type.name} is {ps.level}.")
            else:
                await interaction.response.send_message(f"You haven't set a level for {ship}.", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="setship", description="Set your level for a ship design")
    @app_commands.autocomplete(ship=ship_autocomplete)
    async def setship(self, interaction: discord.Interaction, ship: str, level: int):
        session = get_session()
        try:
            ship_type = session.get(ShipType, ship)
            if not ship_type:
                await interaction.response.send_message("Unknown ship. Pick one from the autocomplete list.", ephemeral=True)
                return
            if not (1 <= level <= ship_type.max_level):
                await interaction.response.send_message(
                    f"{ship_type.name} only goes up to level {ship_type.max_level}.", ephemeral=True
                )
                return

            player = get_or_create_player(session, interaction.guild, interaction.user)
            stmt = select(PlayerShip).where(PlayerShip.player_id == player.id, PlayerShip.ship_key == ship)
            ps = session.execute(stmt).scalar_one_or_none()
            if ps:
                ps.level = level
            else:
                session.add(PlayerShip(player_id=player.id, ship_key=ship, level=level))
            session.commit()
            await interaction.response.send_message(f"Set **{ship_type.name}** to level **{level}**.", ephemeral=True)
        finally:
            session.close()

    # ---------- lookup ----------

    @app_commands.command(name="searchmod", description="Search for a mod by name or alias")
    @app_commands.autocomplete(mod=mod_autocomplete)
    async def searchmod(self, interaction: discord.Interaction, mod: str):
        session = get_session()
        try:
            mod_type = resolve_mod(session, mod)
            if not mod_type:
                await interaction.response.send_message("No matching mod found.", ephemeral=True)
                return
            stmt = select(PlayerMod).where(PlayerMod.mod_key == mod_type.key).order_by(PlayerMod.level.desc())
            mods = session.execute(stmt).scalars().all()
            lines = [f"{pm.player.display_name}: level {pm.level}" for pm in mods]
            color = SLOT_TYPE_COLORS.get(mod_type.slot_type, discord.Color.blurple())
            embed = discord.Embed(title=f"Mod: {mod_type.name}", description="\n".join(lines) or "No players have set this mod yet.", color=color)
            await interaction.response.send_message(embed=embed)
        finally:
            session.close()

    @app_commands.command(name="searchship", description="Search for a ship design by name")
    @app_commands.autocomplete(ship=ship_autocomplete)
    async def searchship(self, interaction: discord.Interaction, ship: str):
        session = get_session()
        try:
            ship_type = session.get(ShipType, ship)
            if not ship_type:
                await interaction.response.send_message("No matching ship found.", ephemeral=True)
                return
            
            stmt = select(PlayerShip).where(PlayerShip.ship_key == ship_type.key).order_by(PlayerShip.level.desc())
            ships = session.execute(stmt).scalars().all()
            lines = [f"{ps.player.display_name}: level {ps.level}" for ps in ships]
            embed = discord.Embed(title=f"Ship: {ship_type.name}", description="\n".join(lines) or "No players have set this ship yet.")
            await interaction.response.send_message(embed=embed)
        finally:
            session.close()

    @app_commands.command(name="profile", description="Show a player's tracked mod/ship levels")
    @app_commands.describe(
        member="Whose profile to show (defaults to you)",
        public="Show this to everyone in the channel? Defaults to public for your own profile, private for others'",
    )
    async def profile(self, interaction: discord.Interaction, member: discord.Member | None = None, public: bool | None = None):
        member = member or interaction.user
        ephemeral = not public if public is not None else member.id != interaction.user.id
        session = get_session()
        try:
            stmt = select(Player).where(Player.guild_id == interaction.guild.id, Player.discord_user_id == member.id)
            player = session.execute(stmt).scalar_one_or_none()
            if not player:
                await interaction.response.send_message(f"No data tracked for {member.display_name} yet.", ephemeral=True)
                return

            embeds = [discord.Embed(title=f"{member.display_name}'s stats", color=discord.Color.blurple())]

            if player.ships:
                ship_lines = "\n".join(f"{ps.ship_type.name}: {ps.level}" for ps in sorted(player.ships, key=lambda ps: ps.ship_type.name))
                embeds[0].add_field(name="🚀 Ships", value=ship_lines, inline=False)

            mods_by_slot = {}
            for pm in player.mods:
                mods_by_slot.setdefault(pm.mod_type.slot_type or "Other", []).append(pm)

            first_mod_embed = True
            for slot_type in SLOT_TYPE_ORDER + sorted(set(mods_by_slot) - set(SLOT_TYPE_ORDER)):
                mods = mods_by_slot.get(slot_type)
                if not mods:
                    continue
                mod_lines = "\n".join(f"{pm.mod_type.name}: {pm.level}" for pm in sorted(mods, key=lambda pm: pm.mod_type.name))
                color = SLOT_TYPE_COLORS.get(slot_type, discord.Color.blurple())
                embed = discord.Embed(title=slot_type, description=mod_lines, color=color)
                if first_mod_embed:
                    embed.set_author(name="⚙️ Modules")
                    first_mod_embed = False
                embeds.append(embed)

            if not player.ships and not player.mods:
                embeds[0].description = "No mod/ship levels recorded yet."

            await interaction.response.send_message(embeds=embeds, ephemeral=ephemeral)
        finally:
            session.close()

    @app_commands.command(name="leaderboard", description="Top players for a given mod or ship")
    @app_commands.autocomplete(stat=mod_autocomplete)  # user picks mods; ship leaderboard below is separate
    async def leaderboard(self, interaction: discord.Interaction, stat: str):
        session = get_session()
        try:
            mod_type = session.get(ModType, stat)
            if not mod_type:
                await interaction.response.send_message("Unknown mod.", ephemeral=True)
                return

            stmt = (
                select(Player, PlayerMod.level)
                .join(PlayerMod, PlayerMod.player_id == Player.id)
                .where(Player.guild_id == interaction.guild.id, PlayerMod.mod_key == stat)
                .order_by(PlayerMod.level.desc())
                .limit(10)
            )
            rows = session.execute(stmt).all()
            if not rows:
                await interaction.response.send_message(f"No data for {mod_type.name} yet.")
                return

            lines = [f"{i+1}. {p.display_name} — level {lvl}" for i, (p, lvl) in enumerate(rows)]
            embed = discord.Embed(title=f"Leaderboard: {mod_type.name}", description="\n".join(lines))
            await interaction.response.send_message(embed=embed)
        finally:
            session.close()

    # ---------- timezone ----------
    @app_commands.command(name="settimezone", description="Set your timezone")
    @app_commands.autocomplete(timezone=timezone_autocomplete)
    async def settimezone(self, interaction: discord.Interaction, timezone: str):
        if timezone not in available_timezones():
            await interaction.response.send_message(
                "Unknown timezone. Pick one from the autocomplete list (e.g. `America/New_York`, `Europe/London`).",
                ephemeral=True,
            )
            return

        session = get_session()
        try:
            player = get_or_create_player(session, interaction.guild, interaction.user)
            player.timezone = timezone
            session.commit()
            now = datetime.now(ZoneInfo(timezone)).strftime("%I:%M %p")
            await interaction.response.send_message(f"Timezone set to **{timezone}** — it's currently {now} there.", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="gettimezone", description="Get your (or someone else's) timezone")
    async def gettimezone(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        session = get_session()
        try:
            player = get_or_create_player(session, interaction.guild, member)
            if not player.timezone:
                await interaction.response.send_message(f"{member.display_name} hasn't set a timezone yet.", ephemeral=True)
                return
            now = datetime.now(ZoneInfo(player.timezone)).strftime("%I:%M %p")
            await interaction.response.send_message(f"**{member.display_name}**'s timezone is **{player.timezone}** — currently {now} there.", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="time", description="Show the current time for everyone who has set a timezone")
    async def time(self, interaction: discord.Interaction):
        session = get_session()
        try:
            stmt = select(Player).where(Player.guild_id == interaction.guild.id, Player.timezone.is_not(None))
            players = session.execute(stmt).scalars().all()
            if not players:
                await interaction.response.send_message("No one has set a timezone yet.", ephemeral=True)
                return

            rows = []
            for p in players:
                now = datetime.now(ZoneInfo(p.timezone))
                rows.append((now.utcoffset(), f"{p.display_name} — {p.timezone} ({now.strftime('%I:%M %p')})"))
            rows.sort(key=lambda r: r[0])

            embed = discord.Embed(title="Timezones", description="\n".join(line for _, line in rows), color=discord.Color.blurple())
            await interaction.response.send_message(embed=embed)
        finally:
            session.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Players(bot))
