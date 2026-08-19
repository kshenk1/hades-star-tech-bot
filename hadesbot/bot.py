import asyncio
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

from db.database import init_db
from db.seed import seed

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # needed to resolve display names reliably

bot = commands.Bot(command_prefix="!htb", intents=intents)

COGS = ["cogs.players", "cogs.admin", "cogs.help"]

MODE = os.getenv("MODE", "test").lower()

if MODE not in ["test", "team-elite", "prod"]:
    raise ValueError("MODE must be one of 'test', 'team-elite', or 'prod'")

MY_TEST_GUILD_ID = os.getenv("MY_TEST_GUILD_ID", "")
TEAM_ELITE_GUILD_ID = os.getenv("TEAM_ELITE_GUILD_ID", "")
GUILD_ID = None

if MODE == "test":
    GUILD_ID = MY_TEST_GUILD_ID
elif MODE == "team-elite":
    GUILD_ID = TEAM_ELITE_GUILD_ID

if GUILD_ID is None and MODE != "prod":
    raise ValueError("MY_TEST_GUILD_ID or TEAM_ELITE_GUILD_ID must be set in .env for test or team-elite mode")

async def load_cogs():
    for ext in COGS:
        await bot.load_extension(ext)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    if MODE in ["test", "team-elite"]:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} slash commands to {GUILD_ID} guild")
    elif MODE == "prod":
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")


async def main():
    init_db()
    seed()  # idempotent — upserts mod/ship reference data on every boot
    async with bot:
        await load_cogs()
        await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
