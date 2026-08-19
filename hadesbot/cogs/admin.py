import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import func, select

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
