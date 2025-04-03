import os

import dotenv
import discord
from discord.ext import commands

dotenv.load_dotenv()

bot = commands.Bot("yomiage#")


@bot.event
async def setup_hook():
    await bot.load_extension("cogs.yomiage")
    await bot.load_extension("cogs.speakers")


bot.run(os.getenv("discord"))
