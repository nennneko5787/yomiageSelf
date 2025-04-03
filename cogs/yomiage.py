import asyncio

import discord
import httpx
from discord.ext import commands


class YomiageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.yomiChannel: dict[int, discord.abc.Messageable] = {}
        self.queue: dict[int, asyncio.Queue] = {}
        self.playing: dict[int, bool] = {}
        self.speaker: dict[int, int] = {}
        self.http: httpx.AsyncClient = httpx.AsyncClient()

    async def yomiage(self, guild: discord.Guild):
        if self.queue[guild.id].qsize() <= 0:
            if guild.voice_client is not None:
                self.playing[guild.id] = False
            return
        mp3Url = await self.queue[guild.id].get()

        options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
        }
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(mp3Url, **options), 2.0
        )

        voiceClient: discord.VoiceClient = guild.voice_client

        loop = asyncio.get_event_loop()

        def after(e: Exception):
            if voiceClient.is_playing():
                voiceClient.stop()
            if voiceClient.is_connected():
                asyncio.run_coroutine_threadsafe(asyncio.sleep(2), loop=loop)
                asyncio.run_coroutine_threadsafe(self.yomiage(guild), loop=loop)

        voiceClient.play(source, after=after)
        self.playing[guild.id] = True

    async def generateTalk(self, guild: discord.Guild, text: str):
        while True:
            response = await self.http.get(
                f"https://api.tts.quest/v3/voicevox/synthesis?text={text}&speaker={self.speaker[guild.id]}"
            )
            jsonData = response.json()
            if jsonData.get("retryAfter") is not None:
                await asyncio.sleep(jsonData.get("retryAfter"))
            else:
                break
            await asyncio.sleep(0)
        statusUrl = jsonData["audioStatusUrl"]
        mp3Url = jsonData["mp3DownloadUrl"]
        while True:
            response = await self.http.get(statusUrl)
            jsonData = response.json()
            if jsonData["isAudioReady"]:
                break
            if jsonData["isAudioError"]:
                break
            if not jsonData["success"]:
                break
            if jsonData.get("retryAfter") is not None:
                await asyncio.sleep(jsonData.get("retryAfter"))
            await asyncio.sleep(1)
        await self.queue[guild.id].put(mp3Url)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content.startswith(self.bot.command_prefix):
            return
        if message.author.bot:
            return
        channel = self.yomiChannel.get(message.guild.id)
        if channel and channel.id == message.channel.id:
            await self.generateTalk(
                message.guild,
                f"{message.author.display_name}、さん、{message.clean_content}",
            )
            if not self.playing[message.guild.id]:
                await self.yomiage(message.guild)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        guild = member.guild
        channel = self.yomiChannel.get(guild.id)
        if not channel:
            return

        if before.channel:
            if before.channel.id != channel.id:
                return
            if after.channel is None:
                await self.generateTalk(
                    guild,
                    f"{member.display_name}、さんが退出しました。",
                )
                if not self.playing[guild.id]:
                    await self.yomiage(guild)
            elif after.channel.id == channel.id:
                await self.generateTalk(
                    guild,
                    f"{member.display_name}、さんが入室しました。",
                )
                if not self.playing[guild.id]:
                    await self.yomiage(guild)
        else:
            if after.channel.id == channel.id:
                await self.generateTalk(
                    guild,
                    f"{member.display_name}、さんが入室しました。",
                )
                if not self.playing[guild.id]:
                    await self.yomiage(guild)

    @commands.command()
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice.channel:
            await ctx.message.add_reaction("❌")
            return
        if ctx.voice_client:
            await ctx.message.add_reaction("❌")
            return
        self.yomiChannel[ctx.guild.id] = ctx.channel
        self.queue[ctx.guild.id] = asyncio.Queue()
        self.playing[ctx.guild.id] = False
        self.speaker[ctx.guild.id] = 1
        await ctx.author.voice.channel.connect()

        await self.generateTalk(
            ctx.guild,
            f"接続しました。",
        )
        await self.yomiage(ctx.guild)

    @commands.command()
    async def leave(self, ctx: commands.Context):
        if not ctx.voice_client:
            await ctx.message.add_reaction("❌")
            return
        del self.yomiChannel[ctx.guild.id]
        del self.queue[ctx.guild.id]
        del self.playing[ctx.guild.id]
        del self.speaker[ctx.guild.id]
        await ctx.voice_client.disconnect()

    @commands.command(name="speaker")
    async def speakerCommand(self, ctx: commands.Context, speaker: int = 1):
        if not ctx.voice_client:
            await ctx.message.add_reaction("❌")
            return
        self.speaker[ctx.guild.id] = speaker
        await ctx.message.add_reaction("⭕")


async def setup(bot: commands.Bot):
    await bot.add_cog(YomiageCog(bot))
