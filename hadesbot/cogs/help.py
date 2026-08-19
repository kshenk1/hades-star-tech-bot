import discord
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="howard-help", description="Show how to use this bot")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Hades Star Tech Bot",
            description="Track your mod and ship design levels, and see how you stack up against the rest of the server.",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="⚙️ Mods",
            value=(
                "`/listmods <type>` — browse every mod in a category (Mining, Transport, Weapon, Shield, Combat, Drone)\n"
                "`/mods` — your mods and their levels\n"
                "`/getmod <mod>` — your level for one mod\n"
                "`/setmod <mod> <level>` — set your level for one mod\n"
                "`/setmods <name:level, ...>` — set several mods at once, e.g. `cargobay:11, crunch:12`\n"
                "`/searchmod <mod>` — see everyone's level for a mod"
            ),
            inline=False,
        )
        embed.add_field(
            name="🚀 Ships",
            value=(
                "`/ships` — your ship designs and levels\n"
                "`/getship <ship>` — your level for one ship\n"
                "`/setship <ship> <level>` — set your level for one ship\n"
                "`/searchship <ship>` — see everyone's level for a ship"
            ),
            inline=False,
        )
        embed.add_field(
            name="📊 Stats",
            value=(
                "`/profile [member] [public]` — full mod/ship rundown for you or someone else\n"
                "  ↳ your own profile posts publicly by default, others' privately — set `public` to override either way\n"
                "`/leaderboard <mod>` — top 10 players for a mod"
            ),
            inline=False,
        )
        embed.add_field(
            name="🕒 Timezone",
            value=(
                "`/settimezone <timezone>` — set your timezone (e.g. `America/New_York`)\n"
                "`/gettimezone [member]` — see your (or someone else's) timezone and local time\n"
                "`/time` — show the current time for everyone who's set a timezone, sorted by local time"
            ),
            inline=False,
        )
        if interaction.user.guild_permissions.manage_guild:
            embed.add_field(
                name="🛡️ Admin (Manage Server)",
                value=(
                    "`/setofficerrole <role>` — set which role can edit other players' stats\n"
                    "`/modusers` — list players who have entered mod data\n"
                    "`/userdata <member>` — dump everything tracked for a player\n"
                    "`/purgeuser <member> confirm:True` — permanently delete a player's data\n"
                    "`/warroster <members>` — @-mention a set of players (e.g. your White Star Battle lineup) "
                    "for a combined timezone + mod/ship rundown, sorted by local time"
                ),
                inline=False,
            )

        embed.set_footer(text="Tip: mod/ship names autocomplete as you type, and most mods accept short aliases too.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
