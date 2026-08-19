import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select
from zoneinfo import ZoneInfo
import re
from datetime import datetime

from db.database import get_session
from db.models import Guild, Player, PlayerMod


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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

    # ---------- roster ----------
    @app_commands.command(name="warroster", description="[Admin] Timezone + mod/ship rundown for a set of players, e.g. a White Star Battle roster")
    @app_commands.describe(members="@-mention everyone who's confirmed, e.g. @Alice @Bob @Carol")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def warroster(self, interaction: discord.Interaction, members: str):
        member_ids = [int(uid) for uid in re.findall(r"<@!?(\d+)>", members)]
        if not member_ids:
            await interaction.response.send_message("Mention at least one player, e.g. `@Alice @Bob`.", ephemeral=True)
            return

        await interaction.response.defer()

        resolved, unresolved = [], []
        for uid in member_ids:
            member = interaction.guild.get_member(uid)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(uid)
                except discord.NotFound:
                    unresolved.append(uid)
                    continue
            resolved.append(member)

        session = get_session()
        try:
            rows = []
            for member in resolved:
                stmt = select(Player).where(Player.guild_id == interaction.guild.id, Player.discord_user_id == member.id)
                player = session.execute(stmt).scalar_one_or_none()

                if player and player.timezone:
                    now = datetime.now(ZoneInfo(player.timezone))
                    tz_display = f"{player.timezone} ({now.strftime('%I:%M %p')})"
                    sort_key = (0, now.utcoffset())
                else:
                    tz_display = "no timezone set"
                    sort_key = (1, member.display_name)

                if player and player.mods:
                    mod_lines = ", ".join(f"{pm.mod_type.name} {pm.level}" for pm in sorted(player.mods, key=lambda pm: pm.mod_type.name))
                else:
                    mod_lines = "none tracked"
                if player and player.ships:
                    ship_lines = ", ".join(f"{ps.ship_type.name} {ps.level}" for ps in sorted(player.ships, key=lambda ps: ps.ship_type.name))
                else:
                    ship_lines = "none tracked"

                rows.append((sort_key, member.display_name, tz_display, mod_lines, ship_lines))

            rows.sort(key=lambda r: r[0])

            embed = discord.Embed(title=f"⚔️ White Star Battle Roster ({len(rows)})", color=discord.Color.red())
            for _, name, tz_display, mod_lines, ship_lines in rows:
                value = f"**Mods:** {mod_lines}\n**Ships:** {ship_lines}"
                if len(value) > 1024:
                    value = value[:1021] + "..."
                embed.add_field(name=f"{name} — {tz_display}", value=value, inline=False)

            if unresolved:
                embed.set_footer(text=f"Couldn't resolve {len(unresolved)} mention(s) — they may have left the server.")

            await interaction.followup.send(embed=embed)
        finally:
            session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
