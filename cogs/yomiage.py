import asyncio
import json
import re
from pathlib import Path
from voicevox_core.asyncio import Onnxruntime, OpenJtalk, Synthesizer, VoiceModelFile
import io
import subprocess

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
        self.voicevox: Synthesizer = None

    async def cog_load(self):
        OpenJtalkDictDir = "./open_jtalk_dic_utf_8-1.11"
        self.voicevox = Synthesizer(
            await Onnxruntime.load_once(), await OpenJtalk.new(OpenJtalkDictDir)
        )

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
        if not self.voicevox.is_loaded_voice_model(self.speaker[guild.id]):
            async with await VoiceModelFile.open(
                f"models/vvms/{self.speaker[guild.id]}.vvm"
            ) as model:
                await self.voicevox.load_voice_model(model)
        waveBytes = await self.voicevox.tts(content, self.speaker[guild.id])
        wavIO = io.BytesIO(waveBytes)
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(wavIO), 2.0)

        voiceClient: discord.VoiceClient = guild.voice_client

        loop = asyncio.get_event_loop()

        def after(e: Exception):
            if voiceClient.is_playing():
                voiceClient.stop()
            if voiceClient.is_connected():
                asyncio.run_coroutine_threadsafe(self.yomiage(guild), loop=loop)

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
            content = re.sub(r"<#.*?>", "、チャンネル省略、", content)
            content = re.sub(r"<@.*?>", "、メンション省略、", content)
            content = re.sub(r"<@&.*?>", "、ロールメンション省略、", content)
            content = re.sub(r"<.*?:.*?>", "、絵文字省略、", content)
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

        # どちらのチャンネルにもいない（何も変化していない）場合は無視
        if before.channel is None and after.channel is None:
            return

        # 読み上げ対象のチャンネルからの退出処理
        if before.channel and before.channel.id == channel.id:
            if after.channel is None or after.channel.id != channel.id:
                await self.queue[guild.id].put(
                    f"{member.display_name}さんが退出しました。"
                )
                await self.yomiage(guild)

        # 読み上げ対象のチャンネルへの入室処理
        if (
            after.channel
            and after.channel.id == channel.id
            and (before.channel is None or before.channel.id != channel.id)
        ):
            await self.queue[guild.id].put(f"{member.display_name}さんが入室しました。")
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
