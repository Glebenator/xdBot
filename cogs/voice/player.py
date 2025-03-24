# cogs/voice/player.py
"""Music player class for handling playback and queue management."""

import discord
import asyncio
from async_timeout import timeout
import logging
from .track import Track
from .utils.ytdl import YTDLSource
from .utils.config import PLAYER_TIMEOUT

# Setup logger
logger = logging.getLogger(__name__)

class MusicPlayer:
    """Manages the music queue and playback for a guild."""

    def __init__(self, ctx):
        """
        Initialize a MusicPlayer.
        
        Args:
            ctx: Command context
        """
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.current = None
        self.loop_mode = 'off'  # 'off', 'single', 'queue'
        self.skip_votes = set()  # Users who voted to skip
        self.player_task = ctx.bot.loop.create_task(self.player_loop())
        
    async def add_track(self, track):
        """
        Add a track to the queue.
        
        Args:
            track: Track to add
        """
        await self.queue.put(track)
        return self.queue.qsize()
        
    async def get_tracks(self, limit=None):
        """
        Get all tracks in the queue.
        
        Args:
            limit: Maximum number of tracks to return
            
        Returns:
            list: List of tracks in the queue
        """
        tracks = list(self.queue._queue)
        if limit:
            return tracks[:limit]
        return tracks
        
    def clear_queue(self):
        """Clear the music queue."""
        self.queue._queue.clear()
        
    def remove_track(self, index):
        """
        Remove a track at the specified index.
        
        Args:
            index: Index of track to remove (0-based)
            
        Returns:
            Track: Removed track or None if index is invalid
        """
        if 0 <= index < len(self.queue._queue):
            items = list(self.queue._queue)
            removed_item = items[index]
            
            # Clear the queue
            self.queue._queue.clear()
            
            # Add back all items except the one to remove
            for i, item in enumerate(items):
                if i != index:
                    self.queue._queue.append(item)
                    
            return removed_item
        return None

    async def player_loop(self):
        """Main player loop that handles playback of songs."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()
            self.skip_votes.clear()

            # Try to get the next song within timeout period
            try:
                async with timeout(PLAYER_TIMEOUT):  # 3 minutes
                    if self.loop_mode == 'single' and self.current:
                        # Re-create the source for the same track
                        source = await YTDLSource.create_source(
                            self.current.url,
                            loop=self.bot.loop,
                            requester=self.current.requester
                        )
                        track = Track(source, self.current.requester)
                    else:
                        # Get next track from queue
                        track = await self.queue.get()
            except asyncio.TimeoutError:
                return self.destroy(self._guild)

            self.current = track

            # Start playing
            try:
                self._guild.voice_client.play(
                    track.source.source,
                    after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set)
                )
                
                # Send a now playing message
                embed = track.to_embed(embed_type="now_playing")
                
                # Add loop mode info
                embed.set_footer(text=f"Loop: {self.loop_mode}")
                
                await self._channel.send(embed=embed)
                
                # Wait for the song to finish
                await self.next.wait()
                
                # If loop mode is 'queue', add the song back to the queue
                if self.loop_mode == 'queue':
                    # Re-create the source for the same track
                    source = await YTDLSource.create_source(
                        self.current.url,
                        loop=self.bot.loop,
                        requester=self.current.requester
                    )
                    track = Track(source, self.current.requester)
                    await self.queue.put(track)
                
                self.current = None
                
            except Exception as e:
                logger.error(f"Player error: {e}")
                await self._channel.send(f"An error occurred during playback: {e}")
                self.current = None
                continue

    def destroy(self, guild):
        """
        Disconnect and cleanup the player.
        
        Args:
            guild: Guild to clean up
        """
        return self.bot.loop.create_task(self._cog.cleanup(guild))
        
    def is_playing(self):
        """Check if the player is currently playing."""
        return self._guild.voice_client and self._guild.voice_client.is_playing()
        
    def is_paused(self):
        """Check if the player is currently paused."""
        return self._guild.voice_client and self._guild.voice_client.is_paused()
        
    def skip(self):
        """Skip the current song."""
        if self.is_playing():
            self._guild.voice_client.stop()
            
    def pause(self):
        """Pause the current song."""
        if self.is_playing():
            self._guild.voice_client.pause()
            
    def resume(self):
        """Resume the current song."""
        if self.is_paused():
            self._guild.voice_client.resume()