import discord
from discord import app_commands
from discord.ext import commands

from db.database import get_session
from db.models import Guild


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


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
