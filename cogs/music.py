"""Run one playback worker for each server."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field

import discord
from discord.ext import commands

from config import settings
from utils.db_handler import get_database_handler
from utils.helpers import defer_hybrid
from utils.music_exceptions import MusicError
from utils.voice_handler import Track, open_audio, resolve_track

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Playback:
    volume: float
    pending: deque[tuple[Track, int]] = field(default_factory=deque)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    worker: asyncio.Task | None = None
    voice: discord.VoiceClient | None = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_database_handler()
        self.sessions: dict[int, Playback] = {}

    def _session(self, guild_id: int) -> Playback:
        if guild_id not in self.sessions:
            self.sessions[guild_id] = Playback(settings.music_default_volume)
        return self.sessions[guild_id]

    @staticmethod
    def _user_channel(ctx):
        voice_state = getattr(ctx.author, "voice", None)
        if voice_state is None or voice_state.channel is None:
            raise MusicError("Join a voice channel first.")
        return voice_state.channel

    def _same_channel(self, ctx) -> discord.VoiceClient:
        channel = self._user_channel(ctx)
        voice = ctx.guild.voice_client
        if voice is None or not voice.is_connected():
            raise MusicError("The bot is not connected to voice.")
        if channel != voice.channel:
            raise MusicError("Join the bot's voice channel first.")
        return voice

    async def _connect(self, ctx) -> discord.VoiceClient:
        channel = self._user_channel(ctx)
        if ctx.guild.voice_client is not None:
            return self._same_channel(ctx)
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.connect or not permissions.speak:
            raise MusicError("The bot needs Connect and Speak permissions in this channel.")
        return await channel.connect(timeout=20)

    def _start_worker(self, guild_id: int, state: Playback, voice: discord.VoiceClient) -> None:
        if state.worker is not None and not state.worker.done() and state.voice is voice:
            return
        if state.worker is not None:
            state.worker.cancel()
        state.voice = voice
        state.worker = asyncio.create_task(self._playback_worker(guild_id, state, voice))

    async def _playback_worker(self, guild_id: int, state: Playback, voice: discord.VoiceClient) -> None:
        try:
            while voice.is_connected():
                async with state.lock:
                    item = state.pending.popleft() if state.pending else None
                    if item is None:
                        state.ready.clear()
                if item is None:
                    try:
                        await asyncio.wait_for(state.ready.wait(), settings.music_idle_timeout)
                    except TimeoutError:
                        async with state.lock:
                            if not state.pending:
                                await voice.disconnect()
                                return
                    continue

                track, requester_id = item
                try:
                    await self._play_track(guild_id, requester_id, track, state, voice)
                except (MusicError, discord.ClientException, OSError) as error:
                    logger.warning("Could not play %s in server %s: %s", track.video_id, guild_id, error)
        except Exception:
            logger.exception("Playback worker failed in server %s", guild_id)

    async def _play_track(self, guild_id, requester_id, track, state, voice):
        audio = await open_audio(track, state.volume)
        loop = asyncio.get_running_loop()
        finished = loop.create_future()

        def finish(error):
            if not finished.done():
                finished.set_result(error)

        def after(error):
            loop.call_soon_threadsafe(finish, error)

        try:
            audio.volume = state.volume
            voice.play(audio, after=after)
        except Exception:
            audio.cleanup()
            raise

        try:
            await self.db.log_music_play(guild_id, requester_id, track.title, track.webpage_url, track.duration)
        except Exception:
            logger.exception("Could not record playback in server %s", guild_id)

        error = await finished
        if error is not None:
            logger.warning("Audio stopped in server %s: %s", guild_id, error)

    @staticmethod
    async def _stop_worker(state: Playback, voice: discord.VoiceClient) -> None:
        state.pending.clear()
        voice.stop()
        if state.worker is not None:
            state.worker.cancel()
            await asyncio.gather(state.worker, return_exceptions=True)
            state.worker = None
            state.voice = None

    async def cog_unload(self) -> None:
        workers = [state.worker for state in self.sessions.values() if state.worker is not None]
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await asyncio.gather(
            *(voice.disconnect(force=True) for voice in list(self.bot.voice_clients)),
            return_exceptions=True,
        )
        self.sessions.clear()

    @commands.hybrid_command(name="join", description="Join your voice channel")
    @commands.guild_only()
    async def join(self, ctx):
        await defer_hybrid(ctx)
        state = self._session(ctx.guild.id)
        async with state.lock:
            voice = await self._connect(ctx)
            self._start_worker(ctx.guild.id, state, voice)
        await ctx.send(f"Connected to {voice.channel.mention}.")

    @commands.hybrid_command(name="play", description="Add a YouTube track to the queue")
    @commands.guild_only()
    async def play(self, ctx, *, query: str):
        await defer_hybrid(ctx)
        self._user_channel(ctx)
        if ctx.guild.voice_client is not None:
            self._same_channel(ctx)
        track = await resolve_track(query)
        state = self._session(ctx.guild.id)
        async with state.lock:
            if len(state.pending) >= settings.music_max_queue_size:
                raise MusicError("The music queue is full.")
            voice = await self._connect(ctx)
            state.pending.append((track, ctx.author.id))
            self._start_worker(ctx.guild.id, state, voice)
            state.ready.set()
        title = discord.utils.escape_markdown(track.title[:200])
        await ctx.send(f"Queued [{title}]({track.webpage_url}).", allowed_mentions=discord.AllowedMentions.none())

    @commands.hybrid_command(name="pause", description="Pause playback")
    @commands.guild_only()
    async def pause(self, ctx):
        voice = self._same_channel(ctx)
        if not voice.is_playing():
            raise MusicError("There is no track playing.")
        voice.pause()
        await ctx.send("Playback paused.")

    @commands.hybrid_command(name="resume", description="Resume playback")
    @commands.guild_only()
    async def resume(self, ctx):
        voice = self._same_channel(ctx)
        if not voice.is_paused():
            raise MusicError("Playback is not paused.")
        voice.resume()
        await ctx.send("Playback resumed.")

    @commands.hybrid_command(name="skip", description="Skip the current track")
    @commands.guild_only()
    async def skip(self, ctx):
        voice = self._same_channel(ctx)
        if not (voice.is_playing() or voice.is_paused()):
            raise MusicError("There is no track to skip.")
        voice.stop()
        await ctx.send("Track skipped.")

    @commands.hybrid_command(name="stop", description="Stop playback and clear the queue")
    @commands.guild_only()
    async def stop(self, ctx):
        await defer_hybrid(ctx)
        state = self._session(ctx.guild.id)
        async with state.lock:
            voice = self._same_channel(ctx)
            await self._stop_worker(state, voice)
            self._start_worker(ctx.guild.id, state, voice)
        await ctx.send("Playback stopped and queue cleared.")

    @commands.hybrid_command(name="volume", description="Set the volume from 0 to 100")
    @commands.guild_only()
    async def volume(self, ctx, volume: commands.Range[int, 0, 100]):
        voice = self._same_channel(ctx)
        state = self._session(ctx.guild.id)
        state.volume = volume / 100
        if isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = state.volume
        await ctx.send(f"Volume set to {volume}%.")

    @commands.hybrid_command(name="leave", aliases=["disconnect", "dc"], description="Leave voice and clear the queue")
    @commands.guild_only()
    async def leave(self, ctx):
        await defer_hybrid(ctx)
        state = self._session(ctx.guild.id)
        async with state.lock:
            voice = self._same_channel(ctx)
            await self._stop_worker(state, voice)
            await voice.disconnect()
        await ctx.send("Disconnected and cleared the queue.")

    async def cog_command_error(self, ctx, error):
        cause = getattr(error, "original", error)
        if isinstance(cause, (MusicError, commands.UserInputError, commands.NoPrivateMessage)):
            await ctx.send(str(cause))
        else:
            logger.error("Music command failed", exc_info=cause)
            await ctx.send("The music command failed. Check the bot log for details.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
