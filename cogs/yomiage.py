import asyncio
import json
import re
import time
import urllib.parse

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

    async def cog_load(self):
        with open("./speakers.json") as f:
            _speaker: dict = json.load(f)
            for index, value in _speaker.items():
                self.speaker[int(index)] = value
        if not isinstance(self.speaker, dict):
            self.speaker = {}

    async def cog_unload(self):
        with open("./speakers.json", "w+") as f:
            json.dump(self.speaker, f)

    async def yomiage(self, guild: discord.Guild):
        if self.queue[guild.id].qsize() <= 0:
            if guild.voice_client is not None:
                self.playing[guild.id] = False
            return
        content = await self.queue[guild.id].get()
        self.playing[guild.id] = True

        while True:
            response = await self.http.get(
                f"https://api.tts.quest/v3/voicevox/synthesis?text={urllib.parse.quote(content)}&speaker={self.speaker[guild.id]}"
            )
            jsonData = response.json()
            if jsonData.get("retryAfter") is not None:
                await asyncio.sleep(jsonData.get("retryAfter"))
            else:
                break
            await asyncio.sleep(0)
        mp3StreamingUrl = jsonData["mp3StreamingUrl"]
        """
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
        """

        options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -bufsize 64k -analyzeduration 2147483647 -probesize 2147483647",
        }
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(mp3StreamingUrl, **options), 2.0
        )

        voiceClient: discord.VoiceClient = guild.voice_client

        loop = asyncio.get_event_loop()

        def after(e: Exception):
            if voiceClient.is_playing():
                voiceClient.stop()
            if voiceClient.is_connected():
                asyncio.run_coroutine_threadsafe(self.yomiage(guild), loop=loop)

        await asyncio.sleep(2)
        voiceClient.play(source, after=after)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content.startswith(self.bot.command_prefix):
            return
        if message.author.bot:
            return
        channel = self.yomiChannel.get(message.guild.id)
        if channel and channel.id == message.channel.id:
            content = message.clean_content
            content = re.sub(r"https?://\S+", "、リンク省略、", content)
            content = re.sub(r"<#.*?>", "、チャンネル、", content)
            content = re.sub(r"<@.*?>", "、メンション、", content)
            content = re.sub(r"<@&.*?>", "、ロールメンション、", content)
            content = re.sub(r"<.*?:.*?>", "、絵文字、", content)
            await self.queue[message.guild.id].put(
                f"{message.author.display_name}さん、{content}{'、添付ファイル' if len(message.attachments) > 0 or len(message.stickers) > 0 else ''}"
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
                await self.queue[guild.id].put(
                    f"{member.display_name}さんが退出しました。"
                )
                await self.yomiage(guild)
            elif after.channel.id == channel.id:
                await self.queue[guild.id].put(
                    f"{member.display_name}さんが入室しました。"
                )
                await self.yomiage(guild)
        else:
            if after.channel.id == channel.id:
                await self.queue[guild.id].put(
                    f"{member.display_name}さんが入室しました。"
                )
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
        if not self.speaker.get(ctx.guild.id):
            self.speaker[ctx.guild.id] = 1
        await ctx.author.voice.channel.connect()

        await self.queue[ctx.guild.id].put("接続しました。")
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
