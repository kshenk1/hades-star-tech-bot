import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from db.database import init_db
from db.seed import seed

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # needed to resolve display names reliably

bot = commands.Bot(command_prefix="!htb", intents=intents)

COGS = ["cogs.players", "cogs.admin"]


async def load_cogs():
    for ext in COGS:
        await bot.load_extension(ext)

TEST_GUILD_ID = "1539155068472008716"

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    guild = discord.Object(id=TEST_GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)
    print(f"Synced {len(synced)} commands to test guild")
    # synced = await bot.tree.sync()
    # print(f"Synced {len(synced)} slash commands")


async def main():
    init_db()
    seed()  # idempotent — upserts mod/ship reference data on every boot
    async with bot:
        await load_cogs()
        await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    asyncio.run(main())
