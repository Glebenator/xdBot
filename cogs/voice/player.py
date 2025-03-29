# cogs/voice/player.py
import discord
import asyncio
# Removed: from async_timeout import timeout # No longer needed for inactivity
import logging
import time
import random
from .track import Track
from .utils.ytdl import YTDLSource
# Removed: from .utils.config import MUSIC_INACTIVITY_TIMEOUT # No longer needed here
from .ui import PlayerControls

logger = logging.getLogger(__name__)

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel # Text channel where commands are initiated / NP messages go
        self._cog = ctx.cog
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        self.current = None
        self.loop_mode = 'off'
        self.skip_votes = set()
        self.volume = 0.5
        self.playback_start_time = None
        self.seek_offset = 0
        self.now_playing_message = None
        self._player_task = self.bot.loop.create_task(self.player_loop())
        self._destroyed = False

    async def add_track(self, track: Track) -> int:
        await self.queue.put(track)
        return self.queue.qsize()

    async def get_tracks(self, limit=None) -> list[Track]:
        tracks = list(self.queue._queue)
        return tracks[:limit] if limit else tracks

    def clear_queue(self):
        # Efficiently clear the queue
        self.queue = asyncio.Queue()
        # If you need to do something with the old items (e.g., logging), iterate:
        # while not self.queue.empty():
        #     try:
        #         self.queue.get_nowait()
        #         self.queue.task_done() # Though task_done isn't strictly needed if replacing queue
        #     except asyncio.QueueEmpty:
        #         break
        #     except Exception as e:
        #         logger.error(f"Error clearing item from queue: {e}")


    def remove_track(self, index: int) -> Track | None:
        if 0 <= index < self.queue.qsize():
            temp_list = list(self.queue._queue)
            removed_track = temp_list.pop(index)
            # Rebuild the queue
            new_queue = asyncio.Queue()
            for track in temp_list:
                new_queue.put_nowait(track)
            self.queue = new_queue
            return removed_track
        return None

    def shuffle_queue(self) -> bool:
        if self.queue.qsize() > 1:
            random.shuffle(self.queue._queue)
            return True
        return False

    def get_progress(self) -> tuple[int | float, int | float]:
        if not all([self.current, self._guild.voice_client, self.playback_start_time]):
             return 0, (self.current.duration_seconds if self.current else 0)

        # If it's a stream or live, duration might be None or 0
        total_seconds = self.current.duration_seconds or 0

        # Get current position from FFmpeg (more accurate than time.time)
        # Note: discord.py's VoiceClient doesn't directly expose FFmpeg's time.
        # We still rely on time.time() unless we implement lower-level FFmpeg interaction.
        elapsed_since_start = time.time() - self.playback_start_time
        current_position = elapsed_since_start + self.seek_offset

        # Clamp position to duration if duration is known
        if total_seconds > 0:
            return min(current_position, total_seconds), total_seconds
        else:
            # For streams/live, return elapsed time and 0 duration (or keep track duration if it was 'LIVE')
             return current_position, (0 if self.current.duration != "LIVE" else "LIVE")


    async def seek(self, seconds: int) -> bool:
        if not self.current or not self._guild.voice_client or self.current.duration == "LIVE":
            logger.warning("Seek attempt failed: No current track, VC, or track is LIVE.")
            return False
        if not self.current.duration_seconds or seconds >= self.current.duration_seconds or seconds < 0:
             logger.warning(f"Seek attempt failed: Invalid seek time {seconds}s for track duration {self.current.duration_seconds}s.")
             return False

        # Stop current playback
        vc = self._guild.voice_client
        vc.stop() # This should trigger the 'after' callback and next.set()

        # Re-create source with seek options
        # NOTE: This approach relies on re-downloading/streaming from the new position.
        # It might be slightly delayed depending on network/source.
        # True FFmpeg seeking requires different interaction.
        original_requester = self.current.requester
        original_url = self.current.url # Use URL as it's more reliable than hoping data persists

        try:
            logger.info(f"Seeking '{self.current.title}' to {seconds} seconds...")
            source_info = await YTDLSource.create_source(
                original_url,
                loop=self.bot.loop,
                stream=True,
                requester=original_requester,
                seek_seconds=seconds # Pass seek time to YTDLSource if it supports it (e.g., via ffmpeg options)
            )
            # Update the current track reference ONLY if source creation succeeds
            self.current = Track(source_info, original_requester)
            source_with_volume = discord.PCMVolumeTransformer(
                self.current.source,
                volume=self.volume
            )

            # Play the new source
            vc.play(
                source_with_volume,
                after=lambda e: self.bot.loop.call_soon_threadsafe(self.next.set) if not e else self._handle_play_error(e)
            )

            # Update timing info
            self.playback_start_time = time.time()
            self.seek_offset = seconds # Store the target seek time

            await self.update_now_playing_message() # Update display immediately
            logger.info(f"Seek successful for '{self.current.title}'.")
            return True

        except Exception as e:
            logger.error(f"Error during seek operation for track {self.current.title if self.current else 'N/A'}: {e}", exc_info=True)
            # If seek fails, we need to signal the loop to potentially try the next track or stop
            self.bot.loop.call_soon_threadsafe(self.next.set) # Move to next state
            return False

    def _handle_play_error(self, error):
        logger.error(f'Player error in after callback: {error}')
        # Signal the loop to continue
        self.bot.loop.call_soon_threadsafe(self.next.set)

    async def update_now_playing_message(self, track: Track | None = None, clear_view=False):
        if self._destroyed:
            return

        display_track = track if track is not None else self.current # Explicitly check for None

        # Case 1: Nothing playing, clear the message
        if not display_track:
            if self.now_playing_message:
                logger.debug(f"Clearing Now Playing message (ID: {self.now_playing_message.id})")
                try:
                    await self.now_playing_message.edit(content="*Playback has ended.*", embed=None, view=None)
                except discord.NotFound:
                    logger.debug("Now Playing message not found during clear, likely deleted.")
                    self.now_playing_message = None # Ensure it's cleared if not found
                except discord.HTTPException as e:
                    logger.warning(f"Failed to clear NP message: {e}")
                    # Optionally retry or just clear the reference
                    self.now_playing_message = None
            return

        # Case 2: Something is playing, update or send the message
        embed = display_track.to_embed(embed_type="now_playing")
        embed.set_footer(text=f"Loop: {self.loop_mode.capitalize()} | Volume: {int(self.volume * 100)}% | Queue: {self.queue.qsize()} tracks")

        current_pos, total_dur_val = self.get_progress()

        # Format progress bar and time info
        try:
            # Need to import these locally if they are in voice_cog.py
            from .voice_cog import format_duration, create_progress_bar

            progress_bar_text = create_progress_bar(current_pos, total_dur_val)

            if display_track.duration == "LIVE" or total_dur_val == "LIVE":
                 time_info = "🔴 LIVE"
                 embed.add_field(name="Progress", value=f"{progress_bar_text} {time_info}", inline=False)
            elif isinstance(total_dur_val, (int, float)) and total_dur_val > 0:
                 time_info = f"{format_duration(current_pos)} / {format_duration(total_dur_val)}"
                 embed.add_field(name="Progress", value=f"{progress_bar_text}\n{time_info}", inline=False)
            else: # Duration unknown or 0, show only progress bar if desired
                 # embed.add_field(name="Progress", value=f"{progress_bar_text} `[Unknown Duration]`", inline=False)
                 # Or omit progress field entirely if duration is unknown
                 pass # Decide if you want to show anything here

        except ImportError:
            logger.error("Could not import formatters for progress bar in player.py")
            embed.add_field(name="Progress", value="`Error loading display utilities`", inline=False)
        except Exception as e:
             logger.error(f"Error creating progress display: {e}", exc_info=True)
             embed.add_field(name="Progress", value="`Error displaying progress`", inline=False)


        # Create or remove the view (controls)
        view = PlayerControls(self, self._cog) if not clear_view else None

        # Send or edit the message
        if self.now_playing_message:
            try:
                await self.now_playing_message.edit(content=None, embed=embed, view=view)
                logger.debug(f"Edited Now Playing message (ID: {self.now_playing_message.id})")
            except discord.NotFound:
                logger.debug("NP message not found on edit, sending new one.")
                self.now_playing_message = None # Clear old reference
                # Fall through to send a new message
            except discord.HTTPException as e:
                logger.error(f"Failed to edit NP message: {e} - Attempting to send new.")
                self.now_playing_message = None
                # Fall through to send a new message

        # Send new message if needed
        if not self.now_playing_message:
            try:
                # Ensure self._channel is valid before sending
                if isinstance(self._channel, discord.TextChannel):
                    self.now_playing_message = await self._channel.send(content=None, embed=embed, view=view)
                    logger.info(f"Sent new Now Playing message (ID: {self.now_playing_message.id}) to channel {self._channel.id}")
                else:
                    logger.error(f"Cannot send Now Playing message: Invalid channel object ({self._channel})")

            except discord.Forbidden:
                 logger.error(f"Cannot send Now Playing message: Missing permissions in channel {self._channel.id if self._channel else 'N/A'}")
                 self.now_playing_message = None # Ensure it's None if send fails
            except Exception as e:
                logger.error(f"Failed to send initial NP message: {e}", exc_info=True)
                self.now_playing_message = None

        # Assign message to view for interaction updates
        if view and self.now_playing_message:
            view.message = self.now_playing_message


    async def player_loop(self):
        await self.bot.wait_until_ready()
        logger.info(f"[PlayerLoop {self._guild.id}] Started.")

        while not self.bot.is_closed() and not self._destroyed:
            self.next.clear()
            next_track = None
            source_for_play = None # Store the source we intend to play

            try:
                # --- Logic to get the next track ---
                if self.loop_mode == 'song' and self.current:
                    # Re-fetch the current song for looping
                    logger.debug(f"[PlayerLoop {self._guild.id}] Looping current song: {self.current.title}")
                    try:
                        source_info = await YTDLSource.create_source(
                            self.current.url, loop=self.bot.loop, requester=self.current.requester, stream=True
                        )
                        next_track = Track(source_info, self.current.requester)
                        source_for_play = next_track.source # Get source early
                    except Exception as e:
                         logger.error(f"[PlayerLoop {self._guild.id}] Failed to re-fetch loop track {self.current.title}: {e}", exc_info=True)
                         # If re-fetching fails, stop looping this song and try queue
                         self.loop_mode = 'off'
                         await self._channel.send(f"⚠️ Failed to loop '{self.current.title}', disabling song loop.", delete_after=15)
                         # Fall through to get from queue normally
                         pass

                # Only get from queue if not looping song or if loop failed
                if not next_track:
                    logger.debug(f"[PlayerLoop {self._guild.id}] Waiting for next track from queue...")
                    # REMOVED TIMEOUT BLOCK - Wait indefinitely
                    next_track = await self.queue.get()
                    self.queue.task_done()
                    logger.debug(f"[PlayerLoop {self._guild.id}] Got track from queue: {next_track.title}")
                    source_for_play = next_track.source # Get source

            except asyncio.CancelledError:
                logger.info(f"[PlayerLoop {self._guild.id}] Cancelled.")
                return # Exit loop cleanly on cancellation
            except Exception as e:
                logger.error(f"[PlayerLoop {self._guild.id}] Unexpected error getting next track: {e}", exc_info=True)
                await asyncio.sleep(5) # Wait before retrying loop iteration
                continue # Go to next iteration

            # --- Check if we successfully got a track and source ---
            if not next_track or not source_for_play:
                logger.warning(f"[PlayerLoop {self._guild.id}] Failed to obtain a valid track or source, continuing loop.")
                self.current = None # Ensure current is cleared if we failed
                await self.update_now_playing_message() # Clear NP display
                continue # Skip playback attempt

            # --- Play the track ---
            self.current = next_track
            self.skip_votes.clear() # Clear votes for the new song
            logger.info(f"[PlayerLoop {self._guild.id}] Now Playing: {self.current.title} (URL: {self.current.url})")

            source_with_volume = discord.PCMVolumeTransformer(source_for_play, volume=self.volume)

            try:
                vc = self._guild.voice_client
                if not vc or not vc.is_connected():
                    logger.warning(f"[PlayerLoop {self._guild.id}] Voice client missing or disconnected before playback. Stopping loop.")
                    self.current = None # Clear current track
                    # No self.destroy() here, let external command handle disconnect
                    return # Exit the loop

                # Play the source
                vc.play(
                    source_with_volume,
                    after=lambda e: self.bot.loop.call_soon_threadsafe(self.next.set) if not e else self._handle_play_error(e)
                )
                self.playback_start_time = time.time()
                self.seek_offset = 0 # Reset seek offset for new track
                await self.update_now_playing_message() # Update NP message for the new track

                logger.debug(f"[PlayerLoop {self._guild.id}] Waiting for track '{self.current.title}' to finish or be skipped...")
                await self.next.wait() # Wait until 'after' callback or skip sets the event
                logger.debug(f"[PlayerLoop {self._guild.id}] Finished waiting for '{self.current.title}'.")

            except discord.ClientException as e:
                logger.error(f"[PlayerLoop {self._guild.id}] Discord client exception during playback setup: {e}")
                if self._channel:
                     try: await self._channel.send(f"Playback error: {e}. Skipping track.")
                     except discord.Forbidden: pass
                # Ensure next is set to proceed even if play fails immediately
                self.bot.loop.call_soon_threadsafe(self.next.set)
                await self.next.wait() # Wait briefly to allow state to settle
            except Exception as e:
                logger.error(f"[PlayerLoop {self._guild.id}] Unexpected error during playback/wait: {e}", exc_info=True)
                if self._channel:
                    try: await self._channel.send(f"An unexpected error occurred: {e}. Skipping track.")
                    except discord.Forbidden: pass
                # Ensure next is set to proceed
                self.bot.loop.call_soon_threadsafe(self.next.set)
                await self.next.wait()


            # --- After track finishes or is skipped ---
            previous_track_title = self.current.title if self.current else "N/A" # Store for logging/queue loop

            # Handle queue looping
            if self.loop_mode == 'queue' and self.current:
                 logger.debug(f"[PlayerLoop {self._guild.id}] Re-queuing '{previous_track_title}' for queue loop.")
                 try:
                     # Re-fetch source info to ensure it's fresh for re-queueing
                     source_info = await YTDLSource.create_source(
                         self.current.url, loop=self.bot.loop, requester=self.current.requester, stream=True
                     )
                     requeued_track = Track(source_info, self.current.requester)
                     await self.queue.put(requeued_track)
                     logger.debug(f"[PlayerLoop {self._guild.id}] Successfully re-queued '{previous_track_title}'.")
                 except Exception as e:
                     logger.error(f"[PlayerLoop {self._guild.id}] Failed to re-queue track '{previous_track_title}': {e}", exc_info=True)
                     if self._channel:
                         try: await self._channel.send(f"⚠️ Failed to re-queue '{previous_track_title}' for loop.", delete_after=15)
                         except discord.Forbidden: pass


            # --- Reset state for next iteration ---
            self.current = None
            self.playback_start_time = None
            self.seek_offset = 0

            # Update NP message if queue is empty and not looping queue (to clear controls)
            if self.queue.empty() and self.loop_mode != 'queue':
                 logger.debug(f"[PlayerLoop {self._guild.id}] Queue is empty after '{previous_track_title}' finished. Clearing NP controls.")
                 await self.update_now_playing_message(clear_view=True) # Keep embed, remove buttons

        # --- Loop Exit ---
        logger.info(f"[PlayerLoop {self._guild.id}] Loop ended (Bot closed or destroyed: {self._destroyed}).")
        # Ensure final cleanup if loop ends unexpectedly
        if not self._destroyed:
            logger.warning(f"[PlayerLoop {self._guild.id}] Loop ended unexpectedly, calling destroy().")
            self.destroy()

    def destroy(self):
        """Cleans up player resources."""
        if self._destroyed:
            return
        self._destroyed = True
        logger.info(f"Destroying player for guild {self._guild.id}")

        # Cancel the player loop task
        if self._player_task and not self._player_task.done():
            self._player_task.cancel()
            logger.debug(f"Cancelled player task for guild {self._guild.id}")

        # Clear the queue
        self.clear_queue()

        # Clear Now Playing message (schedule as task)
        if self.now_playing_message:
            logger.debug(f"Scheduling cleanup for Now Playing message (ID: {self.now_playing_message.id})")
            # Use create_task for fire-and-forget edit
            asyncio.create_task(self._edit_np_message_safe(content="*Playback ended.*", embed=None, view=None), name=f"NPCleanup-{self._guild.id}")


        # Call the cog's cleanup method (which handles disconnect)
        # Important: Ensure this doesn't cause infinite loops if cleanup calls destroy
        if self._cog:
             asyncio.create_task(self._cog.cleanup(self._guild), name=f"CogCleanup-{self._guild.id}")
        else:
            logger.warning(f"Player for guild {self._guild.id} has no cog reference for cleanup.")

        # Nullify references
        self.current = None
        # self._guild, self._channel, self._cog = None, None, None # Keep refs needed by cleanup tasks? Maybe not.

    async def _edit_np_message_safe(self, **kwargs):
        """Safely edits the Now Playing message, handling potential errors."""
        if not self.now_playing_message:
            logger.debug("_edit_np_message_safe called but no message reference exists.")
            return
        try:
            await self.now_playing_message.edit(**kwargs)
            logger.debug(f"Successfully edited NP message (ID: {self.now_playing_message.id}) during cleanup.")
            self.now_playing_message = None # Clear reference after successful edit
        except discord.NotFound:
            logger.debug(f"NP message (ID: {self.now_playing_message.id}) not found during cleanup edit.")
            self.now_playing_message = None
        except discord.HTTPException as e:
            logger.warning(f"Failed to edit NP message (ID: {self.now_playing_message.id}) during cleanup: {e}")
            # Still clear the reference even if edit fails
            self.now_playing_message = None

    # --- Playback State Checks ---
    def is_playing(self) -> bool:
        vc = self._guild.voice_client
        # Check both playing and current track exists, as vc.is_playing() might linger briefly after stop
        return vc and vc.is_playing() and self.current is not None

    def is_paused(self) -> bool:
        vc = self._guild.voice_client
        return vc and vc.is_paused()

    # --- Playback Actions ---
    def pause(self):
        vc = self._guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            logger.info(f"Paused playback in guild {self._guild.id}")

    def resume(self):
        vc = self._guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            logger.info(f"Resumed playback in guild {self._guild.id}")

    def skip(self):
        """Stops the current track, triggering the 'after' callback and player loop progression."""
        self.skip_votes.clear()
        vc = self._guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            logger.info(f"Skipping track in guild {self._guild.id}")
            vc.stop() # Triggers the 'after' callback which sets self.next

    def stop_current(self):
        """Stops playback entirely for the current track, advancing the loop."""
        vc = self._guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
             logger.info(f"Stopping current track explicitly in guild {self._guild.id}")
             vc.stop() # Triggers the 'after' callback which sets self.next