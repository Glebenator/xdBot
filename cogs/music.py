"""Run one playback worker for each server."""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from itertools import islice

import discord
from discord.ext import commands

from config import settings
from utils.db_handler import get_database_handler
from utils.helpers import defer_hybrid
from utils.music_exceptions import MusicError
from utils.voice_handler import Track, open_audio, resolve_track

logger = logging.getLogger(__name__)
LINK_LABEL_ESCAPES = str.maketrans({char: f"\\{char}" for char in "\\*_~|\x60[]"})


@dataclass(frozen=True, slots=True)
class QueuedTrack:
    track: Track
    requester_id: int
    channel: discord.abc.Messageable


@dataclass(slots=True)
class CurrentTrack:
    item: QueuedTrack
    opening: bool = True
    started: bool = False
    skipped: bool = False


@dataclass(slots=True)
class Playback:
    volume: float
    pending: deque[QueuedTrack] = field(default_factory=deque)
    searches: dict[object, discord.VoiceChannel | discord.StageChannel] = field(default_factory=dict)
    current: CurrentTrack | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    worker: asyncio.Task | None = None
    voice: discord.VoiceClient | None = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = get_database_handler()
        self.sessions: dict[int, Playback] = {}
        self.closing = False

    def _session(self, guild_id: int) -> Playback:
        if self.closing:
            raise MusicError("Music is restarting. Try again in a moment.")
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

    def _request_channel(self, ctx, state: Playback):
        channel = self._user_channel(ctx)
        if ctx.guild.voice_client is not None:
            self._same_channel(ctx)
        elif state.searches and channel != next(iter(state.searches.values())):
            raise MusicError("Join the voice channel with the pending music requests first.")
        return channel

    async def _connect(self, ctx) -> discord.VoiceClient:
        if self.closing:
            raise MusicError("Music is restarting. Try again in a moment.")
        channel = self._user_channel(ctx)
        if ctx.guild.voice_client is not None:
            return self._same_channel(ctx)
        permissions = channel.permissions_for(ctx.guild.me)
        if not permissions.connect or not permissions.speak:
            raise MusicError("The bot needs Connect and Speak permissions in this channel.")
        return await channel.connect(timeout=20)

    async def _start_worker(self, guild_id: int, state: Playback, voice: discord.VoiceClient) -> None:
        if state.worker is not None and not state.worker.done() and state.voice is voice:
            return
        await self._cancel_worker(state)
        state.voice = voice
        state.worker = asyncio.create_task(self._playback_worker(guild_id, state, voice))

    async def _playback_worker(self, guild_id: int, state: Playback, voice: discord.VoiceClient) -> None:
        try:
            while voice.is_connected():
                async with state.lock:
                    current = CurrentTrack(state.pending.popleft()) if state.pending else None
                    state.current = current
                    if current is None:
                        state.ready.clear()
                if current is None:
                    try:
                        await asyncio.wait_for(state.ready.wait(), settings.music_idle_timeout)
                    except TimeoutError:
                        async with state.lock:
                            if not state.pending:
                                await voice.disconnect()
                                return
                    continue

                failure = None
                try:
                    await self._play_track(guild_id, current, state, voice)
                except Exception as error:
                    failure = error
                finally:
                    state.current = None
                if failure is not None:
                    await self._report_failure(guild_id, current.item, failure)
        except Exception:
            logger.exception("Playback worker failed in server %s", guild_id)

    @staticmethod
    def _track_link(track: Track) -> str:
        title = (" ".join(track.title.split())[:100] or "YouTube video").translate(LINK_LABEL_ESCAPES)
        return f"[{title}]({track.webpage_url})"

    async def _report_failure(self, guild_id: int, item: QueuedTrack, error: Exception) -> None:
        logger.warning("Could not play %s in server %s: %s", item.track.video_id, guild_id, error)
        reason = str(error) if isinstance(error, MusicError) else "Try a different YouTube video."
        try:
            async with asyncio.timeout(5):
                await item.channel.send(
                    f"Could not play {self._track_link(item.track)}. {reason}",
                    allowed_mentions=discord.AllowedMentions.none(),
                    suppress_embeds=True,
                )
        except Exception:
            logger.exception("Could not report a playback failure in server %s", guild_id)

    async def _play_track(self, guild_id, current: CurrentTrack, state, voice):
        item = current.item
        track = item.track
        audio = await open_audio(track, state.volume)
        loop = asyncio.get_running_loop()
        first_frame = loop.create_future()
        finished = loop.create_future()

        def started():
            if not first_frame.done():
                current.started = True
                first_frame.set_result(None)

        def finish(error):
            if not finished.done():
                finished.set_result(error)

        def after(error):
            loop.call_soon_threadsafe(finish, error)

        try:
            try:
                audio.on_first_frame = lambda: loop.call_soon_threadsafe(started)
                audio.volume = state.volume
                voice.play(audio, after=after)
            except Exception:
                audio.cleanup()
                raise
            current.opening = False
            await asyncio.wait((first_frame, finished), return_when=asyncio.FIRST_COMPLETED)
            if current.started:
                try:
                    await self.db.log_music_play(
                        guild_id, item.requester_id, track.title, track.webpage_url, track.duration,
                    )
                except Exception:
                    logger.exception("Could not record playback in server %s", guild_id)

            error = await finished
            if current.skipped:
                return
            if error is not None:
                raise error
            if not current.started:
                raise MusicError("The stream ended before it sent any audio.")
        finally:
            first_frame.cancel()
            finished.cancel()

    @staticmethod
    async def _cancel_worker(state: Playback) -> None:
        if state.worker is not None:
            state.worker.cancel()
            await asyncio.gather(state.worker, return_exceptions=True)
        state.worker = None
        state.voice = None

    async def _clear_playback(self, ctx, state: Playback) -> discord.VoiceClient | None:
        self._request_channel(ctx, state)
        voice = ctx.guild.voice_client
        if voice is None and not state.searches:
            raise MusicError("The bot is not connected to voice.")
        state.searches.clear()
        state.pending.clear()
        state.ready.clear()
        if voice is not None:
            voice.stop()
        await self._cancel_worker(state)
        return voice

    async def cog_unload(self) -> None:
        self.closing = True
        for state in self.sessions.values():
            async with state.lock:
                state.searches.clear()
                await self._cancel_worker(state)
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
            self._request_channel(ctx, state)
            voice = await self._connect(ctx)
            await self._start_worker(ctx.guild.id, state, voice)
        await ctx.send(f"Connected to {voice.channel.mention}.")

    @commands.hybrid_command(name="play", description="Add a YouTube track to the queue")
    @commands.guild_only()
    async def play(self, ctx, *, query: str):
        await defer_hybrid(ctx)
        state = self._session(ctx.guild.id)
        request = object()
        async with state.lock:
            channel = self._request_channel(ctx, state)
            if len(state.pending) + len(state.searches) >= settings.music_max_queue_size:
                raise MusicError("The music queue is full.")
            state.searches[request] = channel
        try:
            try:
                track = await resolve_track(query)
            except Exception:
                if request not in state.searches:
                    raise MusicError("This music request was canceled.") from None
                raise
            async with state.lock:
                if request not in state.searches:
                    raise MusicError("This music request was canceled.")
                if self._user_channel(ctx) != channel:
                    raise MusicError("Your voice channel changed. Run the command again.")
                voice = await self._connect(ctx)
                await self._start_worker(ctx.guild.id, state, voice)
                if self._user_channel(ctx) != channel:
                    raise MusicError("Your voice channel changed. Run the command again.")
                state.searches.pop(request)
                state.pending.append(QueuedTrack(track, ctx.author.id, ctx.channel))
                position = len(state.pending)
                state.ready.set()
        finally:
            state.searches.pop(request, None)
        await ctx.send(
            f"Queued {self._track_link(track)} at position {position}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def _view_state(self, ctx) -> Playback | None:
        if ctx.guild.voice_client is None:
            return None
        self._same_channel(ctx)
        return self.sessions.get(ctx.guild.id)

    def _current_line(self, ctx, current: CurrentTrack) -> str:
        voice = ctx.guild.voice_client
        if current.skipped:
            status = "Skipping"
        elif voice is not None and voice.is_paused():
            status = "Paused"
        else:
            status = "Playing" if current.started else "Loading"
        return f"**{status}** {self._track_link(current.item.track)}"

    @commands.hybrid_command(name="queue", description="Show the current track and the next five tracks")
    @commands.guild_only()
    async def queue(self, ctx):
        state = self._view_state(ctx)
        if state is None or not (state.current or state.pending):
            await ctx.send("The music queue is empty.")
            return
        lines = [self._current_line(ctx, state.current)] if state.current else []
        lines.extend(f"{i}. {self._track_link(item.track)}" for i, item in enumerate(islice(state.pending, 5), 1))
        if len(state.pending) > 5:
            lines.append(f"{len(state.pending) - 5} more in the queue.")
        await ctx.send("\n".join(lines), allowed_mentions=discord.AllowedMentions.none(), suppress_embeds=True)

    @commands.hybrid_command(name="nowplaying", description="Show the current track and its playback state")
    @commands.guild_only()
    async def nowplaying(self, ctx):
        state = self._view_state(ctx)
        if state is None or state.current is None:
            await ctx.send("There is no current track.")
            return
        await ctx.send(
            self._current_line(ctx, state.current),
            allowed_mentions=discord.AllowedMentions.none(),
            suppress_embeds=True,
        )

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
        await defer_hybrid(ctx)
        state = self._session(ctx.guild.id)
        async with state.lock:
            voice = self._same_channel(ctx)
            current = state.current
            if current is None or current.skipped:
                raise MusicError("There is no track to skip.")
            if current.opening:
                await self._cancel_worker(state)
                await self._start_worker(ctx.guild.id, state, voice)
            elif voice.is_playing() or voice.is_paused():
                current.skipped = True
                voice.stop()
            else:
                raise MusicError("There is no track to skip.")
        await ctx.send("Track skipped.")

    @commands.hybrid_command(name="stop", description="Stop playback and clear the queue")
    @commands.guild_only()
    async def stop(self, ctx):
        await defer_hybrid(ctx)
        state = self._session(ctx.guild.id)
        async with state.lock:
            voice = await self._clear_playback(ctx, state)
            if voice is not None:
                await self._start_worker(ctx.guild.id, state, voice)
        await ctx.send("Playback stopped and queue cleared." if voice is not None else "Music requests cleared.")

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
            voice = await self._clear_playback(ctx, state)
            if voice is not None:
                await voice.disconnect()
        await ctx.send("Disconnected and cleared the queue." if voice is not None else "Music requests cleared.")

    async def cog_command_error(self, ctx, error):
        cause = getattr(error, "original", error)
        if isinstance(cause, (MusicError, commands.UserInputError, commands.NoPrivateMessage)):
            await ctx.send(str(cause))
        else:
            logger.error("Music command failed", exc_info=cause)
            await ctx.send("The music command failed. Check the bot log for details.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
