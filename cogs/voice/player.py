# cogs/voice/player.py
import discord
import asyncio
from async_timeout import timeout
import logging
import time
import random # Added
from .track import Track
from .utils.ytdl import YTDLSource
from .utils.config import PLAYER_TIMEOUT, PLAYER_IDLE_TIMEOUT # Assuming these exist
from .ui import PlayerControls # Added

logger = logging.getLogger(__name__)

class MusicPlayer:
    """Manages the music queue and playback for a guild."""

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel # Text channel context
        self._cog = ctx.cog # Reference to the Voice cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.current = None # The currently playing Track object
        self.loop_mode = 'off'  # 'off', 'song', 'queue'
        self.skip_votes = set()

        # --- New/Modified Attributes ---
        self.volume = 0.5 # Keeping volume attribute even if command isn't added yet
        self.playback_start_time = None # Actual time.time() when playback started
        self.seek_offset = 0 # How many seconds into the track we started (due to seeking)
        self.now_playing_message = None # Message object holding the controls view
        self._player_task = self.bot.loop.create_task(self.player_loop())
        self._destroyed = False


    async def add_track(self, track: Track) -> int:
        """Add a track to the queue. Returns new queue size."""
        await self.queue.put(track)
        return self.queue.qsize()

    async def get_tracks(self, limit=None) -> list[Track]:
        """Get tracks currently in the queue."""
        tracks = list(self.queue._queue)
        return tracks[:limit] if limit else tracks

    def clear_queue(self):
        """Clear the music queue."""
        # self.queue = asyncio.Queue() # Re-create queue or clear internal deque
        while not self.queue.empty():
             try:
                 self.queue.get_nowait()
                 self.queue.task_done()
             except asyncio.QueueEmpty:
                 break
             except Exception as e:
                 logger.error(f"Error clearing item from queue: {e}")

    def remove_track(self, index: int) -> Track | None:
        """Remove a track at the specified index (0-based)."""
        if 0 <= index < self.queue.qsize():
            temp_list = list(self.queue._queue)
            removed_track = temp_list.pop(index)
            self.clear_queue() # Clear internal deque first
            for track in temp_list: # Put remaining back
                self.queue._queue.append(track)
            return removed_track
        return None

    def shuffle_queue(self) -> bool:
        """Shuffles the tracks currently in the queue. Returns True if shuffled."""
        if self.queue.qsize() > 1:
            random.shuffle(self.queue._queue)
            return True
        return False

    def get_progress(self) -> tuple[int, int]:
        """Returns (current_position, total_duration) in seconds."""
        if not self.current or not self.playback_start_time or not self.current.duration_seconds:
            return 0, 0 # Includes LIVE streams (duration_seconds is None)

        total_seconds = self.current.duration_seconds
        elapsed_since_start = time.time() - self.playback_start_time
        current_position = int(elapsed_since_start + self.seek_offset)

        return min(current_position, total_seconds), total_seconds

    async def seek(self, seconds: int) -> bool:
        """Seeks the current track to the specified time in seconds."""
        if not self.current or not self._guild.voice_client or self.current.duration == "LIVE":
            return False # Cannot seek if not playing or live

        original_track_data = self.current.data # Keep original YTDL data
        original_requester = self.current.requester

        try:
            # Stop current playback cleanly
            self._guild.voice_client.stop()

            # Recreate the source with the seek parameter
            # Use the original webpage_url to avoid issues with expired stream URLs
            source_info = await YTDLSource.create_source(
                original_track_data['webpage_url'],
                loop=self.bot.loop,
                stream=True, # Always stream for seeking
                requester=original_requester,
                seek_seconds=seconds
            )

            # Create a new Track object with the seeked source
            # (Overwrites self.current but keeps original metadata conceptually)
            self.current = Track(source_info, original_requester)

            # Apply volume transform
            source_with_volume = discord.PCMVolumeTransformer(self.current.source, volume=self.volume)

            # Play the new source
            self._guild.voice_client.play(
                source_with_volume,
                after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set)
            )

            # Update playback time tracking
            self.playback_start_time = time.time()
            self.seek_offset = seconds

            # Update the Now Playing message if it exists
            await self.update_now_playing_message()

            return True

        except Exception as e:
            logger.error(f"Error during seek for track {self.current.title}: {e}")
            # Attempt to recover by moving to the next track or stopping
            self.bot.loop.call_soon_threadsafe(self.next.set) # Signal loop to potentially move on
            return False


    async def update_now_playing_message(self, track: Track | None = None, clear_view=False):
        """Updates or sends the 'Now Playing' message with controls."""
        if self._destroyed: return # Don't try to update if destroyed

        # Use provided track or the current one
        display_track = track or self.current

        if not display_track: # If nothing is playing, clear the message
            if self.now_playing_message:
                 try:
                     await self.now_playing_message.edit(content="Playback finished.", embed=None, view=None)
                 except discord.NotFound:
                     pass # Message already deleted
                 except Exception as e:
                     logger.warning(f"Failed to clear NP message: {e}")
                 self.now_playing_message = None
            return

        # Create embed
        embed = display_track.to_embed(embed_type="now_playing")
        embed.set_footer(text=f"Loop: {self.loop_mode} | Volume: {int(self.volume * 100)}%") # Assuming volume attr exists

        # Add Progress Bar
        current_pos, total_dur = self.get_progress()
        if total_dur > 0:
             from .voice_cog import format_duration, create_progress_bar # Temporary import (better structure avoids this)
             progress_bar_text = create_progress_bar(current_pos, total_dur)
             time_info = f"{format_duration(current_pos)} / {format_duration(total_dur)}"
             embed.add_field(name="Progress", value=f"{progress_bar_text} {time_info}", inline=False)
        elif display_track.duration == "LIVE":
             embed.add_field(name="Progress", value="🔴 LIVE", inline=False)

        # Create or get view
        view = PlayerControls(self, self._cog) if not clear_view else None

        # Send or edit message
        if self.now_playing_message:
            try:
                await self.now_playing_message.edit(embed=embed, view=view)
            except discord.NotFound: # Message was deleted, send a new one
                self.now_playing_message = await self._channel.send(embed=embed, view=view)
            except Exception as e:
                 logger.error(f"Failed to edit NP message: {e}")
                 # Try sending new message as fallback
                 try:
                      self.now_playing_message = await self._channel.send(embed=embed, view=view)
                 except Exception as send_e:
                      logger.error(f"Also failed to send new NP message: {send_e}")
                      self.now_playing_message = None # Give up
        else:
            try:
                 self.now_playing_message = await self._channel.send(embed=embed, view=view)
            except Exception as e:
                 logger.error(f"Failed to send initial NP message: {e}")
                 self.now_playing_message = None

        # Update the view's internal message reference if it exists
        if view and self.now_playing_message:
             view.message = self.now_playing_message


    async def player_loop(self):
        """Main player loop."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed() and not self._destroyed:
            self.next.clear()
            self.skip_votes.clear()

            next_track = None
            try:
                # --- Handle Loop Modes ---
                if self.loop_mode == 'song' and self.current:
                    # Recreate source for the current track
                    source_info = await YTDLSource.create_source(
                        self.current.url, loop=self.bot.loop, requester=self.current.requester
                    )
                    next_track = Track(source_info, self.current.requester)
                else:
                    # Wait for the next song with timeout
                    async with timeout(PLAYER_TIMEOUT): # e.g., 300 seconds (5 minutes)
                        next_track = await self.queue.get()
                        self.queue.task_done() # Mark task as done

            except asyncio.TimeoutError:
                logger.info(f"Player for guild {self._guild.id} timed out due to inactivity.")
                return self.destroy() # Disconnect after timeout
            except asyncio.CancelledError:
                 logger.info(f"Player loop for guild {self._guild.id} cancelled.")
                 return
            except Exception as e:
                 logger.error(f"Error getting next track in player loop: {e}")
                 await asyncio.sleep(5) # Wait a bit before retrying
                 continue # Go to next loop iteration


            # --- Playback ---
            if not next_track: continue # Should not happen with proper logic, but safety check

            self.current = next_track
            source_with_volume = discord.PCMVolumeTransformer(self.current.source, volume=self.volume)

            try:
                 if not self._guild.voice_client:
                      logger.warning(f"Voice client not found for guild {self._guild.id} during playback.")
                      self.current = None
                      continue

                 self._guild.voice_client.play(
                    source_with_volume,
                    after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set)
                 )
                 self.playback_start_time = time.time()
                 self.seek_offset = 0 # Reset seek offset for new track

                 # Send/Update the Now Playing message with controls
                 await self.update_now_playing_message(track=self.current)

                 # Wait for the song to finish playing
                 await self.next.wait()

            except discord.ClientException as e:
                 logger.error(f"Discord client exception during playback: {e}")
                 await self._channel.send(f"Playback error: {e}. Skipping track.")
            except Exception as e:
                logger.error(f"Unexpected error during playback: {e}")
                await self._channel.send(f"An unexpected error occurred: {e}. Skipping track.")
                # Don't continue loop if error is severe, let next.set handle it

            # --- After Playback ---
            # If loop mode is 'queue', add the just-played song back to the end
            if self.loop_mode == 'queue' and self.current:
                try:
                    # Recreate source needed as streams are consumed
                    source_info = await YTDLSource.create_source(
                        self.current.url, loop=self.bot.loop, requester=self.current.requester
                    )
                    requeued_track = Track(source_info, self.current.requester)
                    await self.queue.put(requeued_track)
                except Exception as e:
                     logger.error(f"Failed to re-queue track for loop: {e}")

            # Clear current track info only AFTER handling queue loop
            self.current = None
            self.playback_start_time = None
            self.seek_offset = 0

            # If queue is empty after song finishes (and not looping queue), update message
            if self.queue.empty() and self.loop_mode != 'queue':
                await self.update_now_playing_message(clear_view=True) # Clear NP message


        # End of loop (bot closing or destroyed)
        logger.debug(f"Player loop ended for guild {self._guild.id}.")
        if not self._destroyed: # Ensure cleanup if loop ends unexpectedly
            self.destroy()


    def destroy(self):
        """Disconnect and cleanup the player resources."""
        if self._destroyed: return
        self._destroyed = True
        logger.info(f"Destroying player for guild {self._guild.id}")

        # Cancel the player task to prevent it from restarting
        if self._player_task and not self._player_task.done():
            self._player_task.cancel()

        # Clean up the Now Playing message view
        if self.now_playing_message:
            asyncio.create_task(self._edit_np_message_safe(view=None))

        # Schedule the cog's cleanup (disconnect, remove from dict)
        return self.bot.loop.create_task(self._cog.cleanup(self._guild))

    async def _edit_np_message_safe(self, **kwargs):
         """Safely edit the now playing message, handling potential errors."""
         if not self.now_playing_message: return
         try:
              await self.now_playing_message.edit(**kwargs)
         except discord.NotFound:
              self.now_playing_message = None # Message gone
         except discord.HTTPException as e:
              logger.warning(f"Failed to edit NP message during cleanup: {e}")
              self.now_playing_message = None # Assume message is problematic


    # --- Control Methods ---
    def is_playing(self) -> bool:
        return self._guild.voice_client and self._guild.voice_client.is_playing()

    def is_paused(self) -> bool:
        return self._guild.voice_client and self._guild.voice_client.is_paused()

    def skip(self):
        """Force skip the current song."""
        self.skip_votes.clear() # Clear votes on forced skip
        if self.is_playing() or self.is_paused():
            self._guild.voice_client.stop() # Triggers the 'after' callback -> next.set()

    def stop_current(self):
         """Stops the current track without clearing the queue immediately."""
         if self.is_playing() or self.is_paused():
             self.loop_mode = 'off' # Turn off looping when stopping explicitly
             self._guild.voice_client.stop()

    def pause(self):
        if self.is_playing():
            self._guild.voice_client.pause()

    def resume(self):
        if self.is_paused():
            self._guild.voice_client.resume()