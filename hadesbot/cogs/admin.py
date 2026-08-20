import csv as csvlib
import io
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

from cogs.players import SHIP_COLORS, SLOT_TYPE_ORDER, get_or_create_player
from db.database import get_session
from db.models import Guild, ModType, Player, PlayerMod, ShipType, WarRoster, WarRosterParticipant


def get_active_ws_roster(session, guild_id: int, role_id: int) -> WarRoster | None:
    stmt = select(WarRoster).where(WarRoster.guild_id == guild_id, WarRoster.role_id == role_id, WarRoster.ended_at.is_(None))
    return session.execute(stmt).scalar_one_or_none()


def find_players_already_in_active_battle(session, guild_id: int, discord_user_ids: list[int]):
    """Players who are already a participant in some OTHER currently-active roster (any role) in this guild."""
    stmt = (
        select(Player.discord_user_id, Player.display_name, WarRoster.role_name)
        .join(WarRosterParticipant, WarRosterParticipant.player_id == Player.id)
        .join(WarRoster, WarRosterParticipant.roster_id == WarRoster.id)
        .where(
            Player.guild_id == guild_id,
            WarRoster.ended_at.is_(None),
            Player.discord_user_id.in_(discord_user_ids),
        )
    )
    return session.execute(stmt).all()


def discord_timestamp(dt: datetime, style: str) -> str:
    return f"<t:{int(dt.replace(tzinfo=timezone.utc).timestamp())}:{style}>"


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ws_roster = app_commands.Group(name="ws-roster", description="[Admin] Manage White Star Battle rosters")

    @app_commands.command(name="setofficerrole", description="Set which role can edit other players' stats")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setofficerrole(self, interaction: discord.Interaction, role: discord.Role):
        session = get_session()
        try:
            g = session.get(Guild, interaction.guild.id)
            if not g:
                g = Guild(id=interaction.guild.id, name=interaction.guild.name)
                session.add(g)
            g.officer_role_id = role.id
            session.commit()
            await interaction.response.send_message(f"Officer role set to {role.mention}.")
        finally:
            session.close()

    @app_commands.command(name="userdata", description="[Admin] Dump all tracked mod/ship data for a player")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def userdata(self, interaction: discord.Interaction, member: discord.Member):
        session = get_session()
        try:
            stmt = select(Player).where(Player.guild_id == interaction.guild.id, Player.discord_user_id == member.id)
            player = session.execute(stmt).scalar_one_or_none()
            if not player:
                await interaction.response.send_message(f"No data tracked for {member.display_name}.", ephemeral=True)
                return

            embed = discord.Embed(title=f"[Admin] {member.display_name}'s data", color=discord.Color.blurple())
            embed.add_field(name="Player ID", value=str(player.id), inline=True)
            embed.add_field(name="Discord User ID", value=str(player.discord_user_id), inline=True)
            embed.add_field(name="Last Updated", value=str(player.updated_at), inline=True)

            mod_lines = "\n".join(f"{pm.mod_type.name}: {pm.level}" for pm in player.mods) or "None"
            ship_lines = "\n".join(f"{ps.ship_type.name}: {ps.level}" for ps in player.ships) or "None"
            embed.add_field(name="Mods", value=mod_lines, inline=False)
            embed.add_field(name="Ships", value=ship_lines, inline=False)

            await interaction.response.send_message(embed=embed, ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="purgeuser", description="[Admin] Permanently delete all tracked data for a player")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def purgeuser(self, interaction: discord.Interaction, member: discord.Member, confirm: bool = False):
        session = get_session()
        try:
            stmt = select(Player).where(Player.guild_id == interaction.guild.id, Player.discord_user_id == member.id)
            player = session.execute(stmt).scalar_one_or_none()
            if not player:
                await interaction.response.send_message(f"No data tracked for {member.display_name}.", ephemeral=True)
                return

            if not confirm:
                await interaction.response.send_message(
                    f"This will permanently delete {len(player.mods)} mod(s) and {len(player.ships)} ship(s) "
                    f"tracked for {member.display_name}. Re-run with `confirm: True` to proceed.",
                    ephemeral=True,
                )
                return

            session.delete(player)
            session.commit()
            await interaction.response.send_message(f"Purged all data for {member.display_name}.", ephemeral=True)
        finally:
            session.close()

    @app_commands.command(name="modusers", description="[Admin] List players who have entered mod data")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modusers(self, interaction: discord.Interaction):
        session = get_session()
        try:
            stmt = (
                select(Player, func.count(PlayerMod.id))
                .join(PlayerMod, PlayerMod.player_id == Player.id)
                .where(Player.guild_id == interaction.guild.id)
                .group_by(Player.id)
                .order_by(Player.display_name)
            )
            rows = session.execute(stmt).all()
            if not rows:
                await interaction.response.send_message("No players have entered mod data yet.", ephemeral=True)
                return

            lines = [f"{player.display_name} — {count} mod(s)" for player, count in rows]
            embed = discord.Embed(
                title=f"[Admin] Players with mod data ({len(rows)})",
                description="\n".join(lines),
                color=discord.Color.blurple(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        finally:
            session.close()

    # ---------- White Star Battle roster ----------
    @ws_roster.command(name="new", description="Start a new White Star Battle roster with 10 players")
    @app_commands.describe(
        role="Discord role to identify this battle — the 10 players get assigned to it",
        **{f"player{i}": f"Participant {i}" for i in range(1, 11)},
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ws_roster_new(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        player1: discord.Member,
        player2: discord.Member,
        player3: discord.Member,
        player4: discord.Member,
        player5: discord.Member,
        player6: discord.Member,
        player7: discord.Member,
        player8: discord.Member,
        player9: discord.Member,
        player10: discord.Member,
    ):
        members = [player1, player2, player3, player4, player5, player6, player7, player8, player9, player10]
        if len({m.id for m in members}) != 10:
            await interaction.response.send_message("All 10 players must be different — you mentioned someone more than once.", ephemeral=True)
            return

        session = get_session()
        try:
            active = get_active_ws_roster(session, interaction.guild.id, role.id)
            if active:
                await interaction.response.send_message(
                    f"A White Star Battle is already in progress for {role.mention} (started {discord_timestamp(active.started_at, 'R')}). "
                    f"Run `/ws-roster end role:{role.name}` first.",
                    ephemeral=True,
                )
                return

            conflicts = find_players_already_in_active_battle(session, interaction.guild.id, [m.id for m in members])
            if conflicts:
                lines = "\n".join(f"- {name} (already in **{role_name}**)" for _, name, role_name in conflicts)
                await interaction.response.send_message(
                    f"Can't start — these players are already in another active battle:\n{lines}",
                    ephemeral=True,
                )
                return

            await interaction.response.defer()

            roster = WarRoster(guild_id=interaction.guild.id, role_id=role.id, role_name=role.name, started_at=datetime.utcnow())
            session.add(roster)
            session.flush()  # need roster.id before FK'd participants

            for member in members:
                player = get_or_create_player(session, interaction.guild, member)
                session.add(WarRosterParticipant(roster_id=roster.id, player_id=player.id))
            session.commit()

            role_failures = []
            for member in members:
                try:
                    await member.add_roles(role, reason="White Star Battle roster started")
                except discord.Forbidden:
                    role_failures.append(member.display_name)

            mentions = " ".join(m.mention for m in members)
            embed = discord.Embed(
                title=f"⚔️ White Star Battle Started — {role.name}",
                description=f"Started {discord_timestamp(roster.started_at, 'R')} ({discord_timestamp(roster.started_at, 'f')})\n\n{mentions}",
                color=discord.Color.red(),
            )
            if role_failures:
                embed.set_footer(text=f"Couldn't assign the role to: {', '.join(role_failures)} — check the bot's role position in Server Settings.")

            await interaction.followup.send(embed=embed)
        finally:
            session.close()

    @ws_roster.command(name="show", description="Show a White Star Battle roster, with a full CSV export")
    @app_commands.describe(role="Which battle to show")
    # @app_commands.checks.has_permissions(manage_guild=True)
    async def ws_roster_show(self, interaction: discord.Interaction, role: discord.Role):
        session = get_session()
        try:
            roster = get_active_ws_roster(session, interaction.guild.id, role.id)
            if not roster:
                await interaction.response.send_message(
                    f"No White Star Battle currently in progress for {role.mention}. Start one with `/ws-roster new`.", ephemeral=True
                )
                return

            await interaction.response.defer()

            participants = (
                session.execute(
                    select(WarRosterParticipant)
                    .where(WarRosterParticipant.roster_id == roster.id)
                    .order_by(WarRosterParticipant.id)
                )
                .scalars()
                .all()
            )

            ship_order = list(SHIP_COLORS.keys())
            ship_types = session.execute(select(ShipType)).scalars().all()
            ship_types.sort(key=lambda st: (ship_order.index(st.key) if st.key in ship_order else len(ship_order), st.name))

            mod_types = session.execute(select(ModType)).scalars().all()
            mod_types.sort(
                key=lambda mt: (
                    SLOT_TYPE_ORDER.index(mt.slot_type) if mt.slot_type in SLOT_TYPE_ORDER else len(SLOT_TYPE_ORDER),
                    mt.name,
                )
            )

            header = ["Player", "Timezone"] + [st.name for st in ship_types] + [mt.name for mt in mod_types]
            csv_rows = [header]
            mentions = []
            for wrp in participants:
                player = wrp.player
                mentions.append(f"<@{player.discord_user_id}>")
                ship_levels = {ps.ship_key: ps.level for ps in player.ships}
                mod_levels = {pm.mod_key: pm.level for pm in player.mods}
                row = [player.display_name, player.timezone or ""]
                row += [str(ship_levels.get(st.key, "")) for st in ship_types]
                row += [str(mod_levels.get(mt.key, "")) for mt in mod_types]
                csv_rows.append(row)

            buffer = io.StringIO()
            writer = csvlib.writer(buffer)
            writer.writerows(csv_rows)
            safe_role_name = "".join(c if c.isalnum() else "-" for c in roster.role_name)
            file = discord.File(io.BytesIO(buffer.getvalue().encode()), filename=f"ws-roster-{safe_role_name}-{roster.started_at:%Y%m%d}.csv")

            embed = discord.Embed(
                title=f"⚔️ White Star Battle In Progress — {roster.role_name}",
                description=f"Started {discord_timestamp(roster.started_at, 'R')} ({discord_timestamp(roster.started_at, 'f')})\n\n{' '.join(mentions)}",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, file=file)
        finally:
            session.close()

    @ws_roster.command(name="end", description="End a White Star Battle roster and record the result")
    @app_commands.describe(
        role="Which battle to end",
        opponent="Who you fought",
        relics_us="Relics we took",
        relics_them="Relics they took",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ws_roster_end(
        self, interaction: discord.Interaction, role: discord.Role, opponent: str, relics_us: int, relics_them: int
    ):
        session = get_session()
        try:
            roster = get_active_ws_roster(session, interaction.guild.id, role.id)
            if not roster:
                await interaction.response.send_message(f"No White Star Battle currently in progress for {role.mention}.", ephemeral=True)
                return

            await interaction.response.defer()

            participants = (
                session.execute(
                    select(WarRosterParticipant)
                    .where(WarRosterParticipant.roster_id == roster.id)
                    .order_by(WarRosterParticipant.id)
                )
                .scalars()
                .all()
            )
            discord_user_ids = [wrp.player.discord_user_id for wrp in participants]

            roster.ended_at = datetime.utcnow()
            roster.opponent = opponent
            roster.relics_us = relics_us
            roster.relics_them = relics_them
            session.commit()

            role_failures = []
            for uid in discord_user_ids:
                member = interaction.guild.get_member(uid)
                if member is None:
                    try:
                        member = await interaction.guild.fetch_member(uid)
                    except discord.NotFound:
                        continue
                try:
                    await member.remove_roles(role, reason="White Star Battle ended")
                except discord.Forbidden:
                    role_failures.append(member.display_name)

            duration = roster.ended_at - roster.started_at
            hours, remainder = divmod(int(duration.total_seconds()), 3600)
            minutes = remainder // 60
            duration_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"

            if relics_us > relics_them:
                result = "🏆 Victory"
            elif relics_us < relics_them:
                result = "💀 Defeat"
            else:
                result = "🤝 Draw"

            embed = discord.Embed(
                title=f"⚔️ White Star Battle Ended — {role.name}",
                description=(
                    f"**{result}** vs **{opponent}** — {relics_us} to {relics_them} relics\n"
                    f"Ran for **{duration_str}**\n"
                    f"Started {discord_timestamp(roster.started_at, 'f')} — Ended {discord_timestamp(roster.ended_at, 'f')}"
                ),
                color=discord.Color.dark_grey(),
            )
            if role_failures:
                embed.set_footer(text=f"Couldn't remove the role from: {', '.join(role_failures)} — check the bot's role position in Server Settings.")

            await interaction.followup.send(embed=embed)
        finally:
            session.close()

    @ws_roster.command(name="factory-reset", description="[Admin] Permanently wipe ALL White Star Battle roster data for this server")
    @app_commands.describe(confirm="Type True to confirm — this cannot be undone")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ws_roster_factory_reset(self, interaction: discord.Interaction, confirm: bool = False):
        session = get_session()
        try:
            rosters = session.execute(select(WarRoster).where(WarRoster.guild_id == interaction.guild.id)).scalars().all()
            if not rosters:
                await interaction.response.send_message("No White Star Battle data to reset for this server.", ephemeral=True)
                return

            active = [r for r in rosters if r.ended_at is None]
            participant_count = sum(len(r.participants) for r in rosters)

            if not confirm:
                await interaction.response.send_message(
                    f"This will permanently delete {len(rosters)} roster(s) ({len(active)} active) and {participant_count} participant "
                    "record(s) for this server, and unassign any in-progress battle roles. Re-run with `confirm: True` to proceed.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True)

            role_failures = []
            for roster in active:
                role = interaction.guild.get_role(roster.role_id)
                if role is None:
                    continue
                for wrp in roster.participants:
                    member = interaction.guild.get_member(wrp.player.discord_user_id)
                    if member is None:
                        continue
                    try:
                        await member.remove_roles(role, reason="White Star Battle roster factory reset")
                    except discord.Forbidden:
                        role_failures.append(member.display_name)

            for roster in rosters:
                session.delete(roster)  # cascade="all, delete-orphan" removes the participant rows too
            session.commit()

            message = f"✅ Factory reset complete — wiped {len(rosters)} roster(s) and {participant_count} participant record(s)."
            if role_failures:
                message += f"\nCouldn't unassign roles from: {', '.join(role_failures)} — check the bot's role position in Server Settings."
            await interaction.followup.send(message, ephemeral=True)
        finally:
            session.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
