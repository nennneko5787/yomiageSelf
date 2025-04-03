import os
import io

import dotenv
import discord
from discord.ext import commands
import httpx

dotenv.load_dotenv()


class SpeakersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http = httpx.AsyncClient()

    @commands.command()
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def speakers(self, ctx: commands.Context):
        s = ""
        response = await self.http.get(
            f"https://deprecatedapis.tts.quest/v2/voicevox/speakers/?key={os.getenv('token')}"
        )
        data = response.json()
        try:
            for speaker in data:
                speakerName = speaker["name"]
                for style in speaker["styles"]:
                    s += f"- {speakerName} ({style['name']}) -> `{style['id']}`\n"
            await ctx.reply(
                file=discord.File(io.BytesIO(s.encode()), filename="speakers.txt")
            )
            with open("speakers.txt", "w+") as f:
                f.write(s)
        except:
            await ctx.reply(file=discord.File("speakers.txt"))


async def setup(bot: commands.Bot):
    await bot.add_cog(SpeakersCog(bot))
