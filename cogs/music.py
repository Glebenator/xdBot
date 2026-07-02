"""Music playback cog with queue management and voice control.

This cog provides commands for playing music in voice channels, including
queue management, playback control, and automatic queue advancement.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

import config
from utils.db_handler import get_database_handler
from utils.helpers import create_embed, defer_hybrid, send_hybrid_message
from utils.music_exceptions import (
    BotNotInVoiceError,
    DifferentVoiceChannelError,
    NotInVoiceChannelError,
    YTDLError,
)
from utils.music_queue import LoopMode, QueueManager, Song
from utils.voice_handler import YTDLSource

logger = logging.getLogger(__name__)


class Music(commands.Cog):
    """Music playback and queue management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue_manager = QueueManager()
        self.db = get_database_handler()
        self.idle_tasks: dict[int, asyncio.Task] = {}  # guild_id -> idle disconnect task

    async def cog_unload(self):
        """Cleanup when cog is unloaded."""
        logger.info("Unloading Music cog, cleaning up voice connections...")

        # Cancel all idle tasks
        for task in self.idle_tasks.values():
            if not task.done():
                task.cancel()

        # Disconnect from all voice channels
        for voice_client in self.bot.voice_clients:
            if voice_client.is_connected():
                await voice_client.disconnect(force=True)
                logger.info(f"Disconnected from guild {voice_client.guild.id}")

        logger.info("Music cog cleanup complete")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _ensure_voice_state(self, ctx: commands.Context) -> discord.VoiceState:
        """Ensure user is in a voice channel.

        Raises:
            NotInVoiceChannelError: If user is not in a voice channel
        """
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise NotInVoiceChannelError()
        return ctx.author.voice

    def _get_voice_client(self, guild: discord.Guild) -> Optional[discord.VoiceClient]:
        """Get the voice client for a guild."""
        return discord.utils.get(self.bot.voice_clients, guild=guild)

    def _ensure_same_channel(self, ctx: commands.Context, voice_client: discord.VoiceClient) -> None:
        """Ensure user and bot are in the same voice channel.

        Raises:
            DifferentVoiceChannelError: If user and bot are in different channels
        """
        if ctx.author.voice.channel != voice_client.channel:
            raise DifferentVoiceChannelError()

    async def _check_voice_permissions(self, channel: discord.VoiceChannel) -> bool:
        """Check if bot has necessary permissions in voice channel."""
        permissions = channel.permissions_for(channel.guild.me)
        return permissions.connect and permissions.speak

    async def _ensure_voice_connection(self, ctx: commands.Context) -> discord.VoiceClient:
        """Ensure bot is connected to the user's voice channel.

        Returns:
            The voice client for the connection

        Raises:
            NotInVoiceChannelError: If user is not in a voice channel
            VoiceConnectionError: If bot cannot connect
        """
        voice_state = self._ensure_voice_state(ctx)
        channel = voice_state.channel

        # Check permissions
        if not await self._check_voice_permissions(channel):
            embed = create_embed(
                title="❌ Missing Permissions",
                description=f"I don't have permission to connect or speak in {channel.mention}",
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
            raise commands.BotMissingPermissions(["connect", "speak"])

        voice_client = self._get_voice_client(ctx.guild)

        if voice_client:
            # Already connected, ensure same channel
            if voice_client.channel != channel:
                await voice_client.move_to(channel)
                logger.info(f"Moved to voice channel: {channel.name} in guild {ctx.guild.id}")
        else:
            # Connect to channel
            voice_client = await channel.connect()
            logger.info(f"Connected to voice channel: {channel.name} in guild {ctx.guild.id}")

        return voice_client

    def _cancel_idle_task(self, guild_id: int) -> None:
        """Cancel the idle disconnect task for a guild."""
        if guild_id in self.idle_tasks:
            task = self.idle_tasks.pop(guild_id)
            if not task.done():
                task.cancel()

    async def _idle_disconnect(self, guild_id: int, timeout: int) -> None:
        """Disconnect from voice after idle timeout."""
        try:
            await asyncio.sleep(timeout)
            voice_client = discord.utils.get(self.bot.voice_clients, guild=self.bot.get_guild(guild_id))
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
                logger.info(f"Disconnected from guild {guild_id} due to inactivity")
        except asyncio.CancelledError:
            pass  # Task was cancelled, normal behavior

    def _play_next(self, guild_id: int) -> None:
        """Play the next song in the queue (callback for after playback)."""
        # Cancel idle task since we're about to play
        self._cancel_idle_task(guild_id)

        # Schedule the async play_next in the event loop
        asyncio.run_coroutine_threadsafe(
            self._async_play_next(guild_id),
            self.bot.loop
        )

    async def _async_play_next(self, guild_id: int) -> None:
        """Async version of play_next to handle queue advancement."""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return

            voice_client = self._get_voice_client(guild)
            if not voice_client or not voice_client.is_connected():
                return

            queue = self.queue_manager.get_queue(guild_id)

            # Handle loop mode
            if queue.loop_mode == LoopMode.SONG and queue.current:
                # Replay current song
                song = queue.current
            else:
                # Get next song
                song = await queue.next()

                # Check if queue is empty
                if song is None:
                    # Queue is empty, start idle timer
                    logger.info(f"Queue empty for guild {guild_id}, starting idle timer")
                    timeout = config.settings.music_idle_timeout
                    self.idle_tasks[guild_id] = asyncio.create_task(
                        self._idle_disconnect(guild_id, timeout)
                    )
                    return

            raw_data = {
                'title': song.title,
                'url': song.url,
                'webpage_url': song.webpage_url,
                'duration': song.duration,
                'thumbnail': song.thumbnail,
                'uploader': song.uploader,
                'http_headers': song.http_headers,
            }

            audio_source: Optional[YTDLSource] = None

            if song.url:
                try:
                    audio_source = YTDLSource.from_stream(
                        song.url,
                        data=raw_data,
                        volume=queue.volume
                    )
                except Exception as e:
                    logger.warning(
                        "Cached stream URL failed for '%s' in guild %s: %s",
                        song.title,
                        guild_id,
                        e,
                    )

            if audio_source is None:
                try:
                    audio_source = await YTDLSource.create_source(
                        song.webpage_url,
                        volume=queue.volume
                    )
                    # Refresh cached metadata with latest stream info
                    song.url = audio_source.url
                    song.duration = audio_source.duration
                    song.http_headers = audio_source.http_headers
                except Exception as e:
                    logger.error(f"Failed to create audio source: {e}")
                    # Try to play next song
                    self._play_next(guild_id)
                    return

            # Play the song
            voice_client.play(
                audio_source,
                after=lambda e: self._handle_playback_error(e, guild_id)
            )

            logger.info(f"Now playing: {song.title} in guild {guild_id}")

            # Record in database
            await self.db.log_music_play(
                guild_id=guild_id,
                user_id=song.requester.id,
                song_title=song.title,
                song_url=song.webpage_url,
                song_duration=song.duration
            )

        except Exception as e:
            logger.error(f"Error in _async_play_next for guild {guild_id}: {e}", exc_info=True)

    def _handle_playback_error(self, error: Optional[Exception], guild_id: int) -> None:
        """Handle errors during playback and advance queue."""
        if error:
            logger.error(f"Playback error in guild {guild_id}: {error}")

        # Always try to play next song
        self._play_next(guild_id)

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------

    @commands.hybrid_command(
        name="join",
        description="Join your voice channel"
    )
    async def join(self, ctx: commands.Context):
        """Join the voice channel you're in."""
        await defer_hybrid(ctx)

        try:
            voice_client = await self._ensure_voice_connection(ctx)

            embed = create_embed(
                title="🎵 Joined Voice Channel",
                description=f"Connected to {voice_client.channel.mention}",
                color=discord.Color.green().value
            )
            await send_hybrid_message(ctx, embed=embed)

        except NotInVoiceChannelError as e:
            embed = create_embed(
                title="❌ Not in Voice Channel",
                description=str(e),
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)

    @commands.hybrid_command(
        name="leave",
        description="Leave the voice channel",
        aliases=["disconnect", "dc"]
    )
    async def leave(self, ctx: commands.Context):
        """Leave the voice channel and clear the queue."""
        await defer_hybrid(ctx)

        voice_client = self._get_voice_client(ctx.guild)

        if not voice_client:
            embed = create_embed(
                title="❌ Not in Voice",
                description="I'm not in a voice channel.",
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
            return

        # Clear queue and disconnect
        self.queue_manager.remove_queue(ctx.guild.id)
        self._cancel_idle_task(ctx.guild.id)

        channel_name = voice_client.channel.name
        await voice_client.disconnect()

        embed = create_embed(
            title="👋 Disconnected",
            description=f"Left {channel_name} and cleared the queue",
            color=discord.Color.blue().value
        )
        await send_hybrid_message(ctx, embed=embed)

    @commands.hybrid_command(
        name="play",
        description="Play a song or add it to the queue"
    )
    async def play(self, ctx: commands.Context, *, query: str):
        """Play a song from YouTube or add it to queue.

        Args:
            query: Song name or YouTube URL to play
        """
        await defer_hybrid(ctx)

        try:
            # Ensure voice connection
            voice_client = await self._ensure_voice_connection(ctx)

            # Get or create queue
            queue = self.queue_manager.get_queue(ctx.guild.id)

            # Extract song info
            try:
                info = await YTDLSource.get_info(query)
            except YTDLError as e:
                embed = create_embed(
                    title="❌ Search Failed",
                    description=f"Could not find or load: {query}\n\n{str(e)}",
                    color=discord.Color.red().value
                )
                await send_hybrid_message(ctx, embed=embed)
                return

            # Create Song object
            song = Song(
                title=info['title'],
                url=info.get('url') or '',
                webpage_url=info['webpage_url'],
                duration=int(info.get('duration') or 0),
                thumbnail=info.get('thumbnail'),
                requester=ctx.author,
                uploader=info.get('uploader'),
                http_headers=info.get('http_headers')
            )

            # Add to queue
            try:
                position = await queue.add(song)
            except Exception as e:
                embed = create_embed(
                    title="❌ Queue Error",
                    description=str(e),
                    color=discord.Color.red().value
                )
                await send_hybrid_message(ctx, embed=embed)
                return

            # If nothing is playing, start playing
            if not voice_client.is_playing() and not voice_client.is_paused():
                self._play_next(ctx.guild.id)

                embed = create_embed(
                    title="🎵 Now Playing",
                    description=f"[{song.title}]({song.webpage_url})",
                    color=discord.Color.green().value
                )
                if song.thumbnail:
                    embed.set_thumbnail(url=song.thumbnail)
                embed.add_field(name="Duration", value=self._format_duration(song.duration), inline=True)
                embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
                if song.uploader:
                    embed.add_field(name="Uploader", value=song.uploader, inline=True)
            else:
                # Added to queue
                embed = create_embed(
                    title="➕ Added to Queue",
                    description=f"[{song.title}]({song.webpage_url})",
                    color=discord.Color.blue().value
                )
                if song.thumbnail:
                    embed.set_thumbnail(url=song.thumbnail)
                embed.add_field(name="Position in Queue", value=f"#{position}", inline=True)
                embed.add_field(name="Duration", value=self._format_duration(song.duration), inline=True)
                embed.add_field(name="Requested by", value=song.requester.mention, inline=True)

            await send_hybrid_message(ctx, embed=embed)

        except NotInVoiceChannelError as e:
            embed = create_embed(
                title="❌ Not in Voice Channel",
                description=str(e),
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)

    @commands.hybrid_command(
        name="pause",
        description="Pause the current song"
    )
    async def pause(self, ctx: commands.Context):
        """Pause the currently playing song."""
        await defer_hybrid(ctx)

        voice_client = self._get_voice_client(ctx.guild)

        if not voice_client or not voice_client.is_connected():
            raise BotNotInVoiceError()

        self._ensure_same_channel(ctx, voice_client)

        if voice_client.is_paused():
            embed = create_embed(
                title="⏸️ Already Paused",
                description="Playback is already paused.",
                color=discord.Color.orange().value
            )
            await send_hybrid_message(ctx, embed=embed)
            return

        if not voice_client.is_playing():
            embed = create_embed(
                title="❌ Nothing Playing",
                description="There's nothing playing right now.",
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
            return

        voice_client.pause()

        embed = create_embed(
            title="⏸️ Paused",
            description="Playback paused.",
            color=discord.Color.blue().value
        )
        await send_hybrid_message(ctx, embed=embed)

    @commands.hybrid_command(
        name="resume",
        description="Resume the paused song"
    )
    async def resume(self, ctx: commands.Context):
        """Resume the paused song."""
        await defer_hybrid(ctx)

        voice_client = self._get_voice_client(ctx.guild)

        if not voice_client or not voice_client.is_connected():
            raise BotNotInVoiceError()

        self._ensure_same_channel(ctx, voice_client)

        if not voice_client.is_paused():
            embed = create_embed(
                title="▶️ Not Paused",
                description="Playback is not paused.",
                color=discord.Color.orange().value
            )
            await send_hybrid_message(ctx, embed=embed)
            return

        voice_client.resume()

        embed = create_embed(
            title="▶️ Resumed",
            description="Playback resumed.",
            color=discord.Color.green().value
        )
        await send_hybrid_message(ctx, embed=embed)

    @commands.hybrid_command(
        name="skip",
        description="Skip the current song"
    )
    async def skip(self, ctx: commands.Context):
        """Skip the currently playing song."""
        await defer_hybrid(ctx)

        voice_client = self._get_voice_client(ctx.guild)

        if not voice_client or not voice_client.is_connected():
            raise BotNotInVoiceError()

        self._ensure_same_channel(ctx, voice_client)

        if not voice_client.is_playing() and not voice_client.is_paused():
            embed = create_embed(
                title="❌ Nothing Playing",
                description="There's nothing to skip.",
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
            return

        queue = self.queue_manager.get_queue(ctx.guild.id)
        current_song = queue.current

        voice_client.stop()  # This will trigger the after callback

        skip_msg = "⏭️ Skipped"
        if current_song:
            skip_msg += f": {current_song.title}"

        embed = create_embed(
            title="⏭️ Skipped",
            description=skip_msg,
            color=discord.Color.blue().value
        )
        await send_hybrid_message(ctx, embed=embed)

    @commands.hybrid_command(
        name="stop",
        description="Stop playback and clear the queue"
    )
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear the queue."""
        await defer_hybrid(ctx)

        voice_client = self._get_voice_client(ctx.guild)

        if not voice_client or not voice_client.is_connected():
            raise BotNotInVoiceError()

        self._ensure_same_channel(ctx, voice_client)

        # Clear queue and stop
        queue = self.queue_manager.get_queue(ctx.guild.id)
        await queue.clear()

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

        embed = create_embed(
            title="⏹️ Stopped",
            description="Playback stopped and queue cleared.",
            color=discord.Color.red().value
        )
        await send_hybrid_message(ctx, embed=embed)

    @commands.hybrid_command(
        name="volume",
        description="Set the playback volume (0-100)"
    )
    async def volume(self, ctx: commands.Context, volume: int):
        """Set the playback volume.

        Args:
            volume: Volume level (0-100)
        """
        await defer_hybrid(ctx)

        voice_client = self._get_voice_client(ctx.guild)

        if not voice_client or not voice_client.is_connected():
            raise BotNotInVoiceError()

        self._ensure_same_channel(ctx, voice_client)

        # Validate volume
        if not 0 <= volume <= 100:
            embed = create_embed(
                title="❌ Invalid Volume",
                description="Volume must be between 0 and 100.",
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
            return

        # Set volume
        queue = self.queue_manager.get_queue(ctx.guild.id)
        queue.volume = volume / 100.0

        # Update current source if playing
        if voice_client.source:
            voice_client.source.volume = queue.volume

        embed = create_embed(
            title="🔊 Volume Changed",
            description=f"Volume set to {volume}%",
            color=discord.Color.green().value
        )
        await send_hybrid_message(ctx, embed=embed)

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format duration in seconds to HH:MM:SS or MM:SS."""
        safe_seconds = int(seconds or 0)

        if safe_seconds <= 0:
            return "Unknown"

        hours = safe_seconds // 3600
        minutes = (safe_seconds % 3600) // 60
        secs = safe_seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    # -------------------------------------------------------------------------
    # Error Handlers
    # -------------------------------------------------------------------------

    @play.error
    @pause.error
    @resume.error
    @skip.error
    @stop.error
    @volume.error
    async def music_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Handle errors for music commands."""
        if isinstance(error, NotInVoiceChannelError):
            embed = create_embed(
                title="❌ Not in Voice Channel",
                description=str(error),
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
        elif isinstance(error, BotNotInVoiceError):
            embed = create_embed(
                title="❌ Bot Not in Voice",
                description=str(error),
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
        elif isinstance(error, DifferentVoiceChannelError):
            embed = create_embed(
                title="❌ Different Voice Channel",
                description=str(error),
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)
        else:
            # Log unexpected errors
            logger.error(f"Unexpected error in music command: {error}", exc_info=error)
            embed = create_embed(
                title="❌ Error",
                description="An unexpected error occurred.",
                color=discord.Color.red().value
            )
            await send_hybrid_message(ctx, embed=embed)


async def setup(bot: commands.Bot):
    """Load the Music cog."""
    await bot.add_cog(Music(bot))
