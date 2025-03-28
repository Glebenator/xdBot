# cogs/voice/voice_cog.py
import discord
from discord.ext import commands
import asyncio
import re # Added
import logging
import time # Added
from utils.helpers import create_embed
from .player import MusicPlayer
from .track import Track
from .utils.ytdl import YTDLSource
from .utils.config import PLAYER_IDLE_TIMEOUT
from .ui import PlayerControls # Added

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def format_duration(seconds: int) -> str:
    """Formats seconds into M:SS or H:MM:SS"""
    if seconds <= 0: return "0:00"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def create_progress_bar(current: int, total: int, length: int = 15) -> str:
    """Creates a text-based progress bar."""
    if total <= 0: return "`[ Unknown Duration ]`"
    percent = max(0.0, min(1.0, current / total)) # Clamp between 0 and 1
    filled_length = int(length * percent)
    bar = '█' * filled_length + '─' * (length - filled_length)
    return f"`[{bar}]`"

# --- Cog ---
class Voice(commands.Cog):
    """Music playback commands."""

    def __init__(self, bot):
        self.bot = bot
        self.players = {}

    def get_player(self, ctx) -> MusicPlayer:
        """Retrieve or create the guild's MusicPlayer."""
        guild_id = ctx.guild.id
        try:
            player = self.players[guild_id]
            # Optional: Update channel if command is used in different one
            # player._channel = ctx.channel
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[guild_id] = player
        return player

    async def cleanup(self, guild):
        """Cleanup player and disconnect."""
        guild_id = guild.id
        try:
            if guild.voice_client:
                 await guild.voice_client.disconnect()
                 logger.info(f"Disconnected from voice in guild {guild_id}")
        except Exception as e:
             logger.error(f"Error disconnecting during cleanup for guild {guild_id}: {e}")

        if guild_id in self.players:
            try:
                player = self.players.pop(guild_id)
                if player and not player._destroyed:
                     player.destroy() # Ensure player resources are freed
                logger.info(f"Removed player for guild {guild_id}")
            except KeyError:
                 pass # Already removed
            except Exception as e:
                 logger.error(f"Error destroying player during cleanup for guild {guild_id}: {e}")

    # --- Listeners ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Handle auto-disconnect and player cleanup."""
        if member.bot and member.id == self.bot.user.id:
            # Bot's own state changed
            if after.channel is None: # Bot was disconnected or left
                 if before.channel: # Check if it was in a channel before
                      logger.info(f"Bot disconnected from {before.channel.name} ({before.channel.guild.id})")
                      await self.cleanup(before.channel.guild)
            return # Ignore other bot state changes

        # Check the channel the bot is currently in (if any)
        voice_client = member.guild.voice_client
        if not voice_client or not voice_client.channel:
            return # Bot is not connected in this guild

        # Check if the change happened in the bot's channel
        if before.channel == voice_client.channel or after.channel == voice_client.channel:
            # Count non-bot members remaining in the bot's channel
            human_members = [m for m in voice_client.channel.members if not m.bot]

            if not human_members: # Bot is alone
                logger.info(f"Bot is alone in {voice_client.channel.name}. Starting idle timer.")
                # Use asyncio.sleep within a task to avoid blocking
                await asyncio.sleep(PLAYER_IDLE_TIMEOUT) # e.g., 180 seconds

                # Re-check after timeout
                # Need to get voice_client again as it might have changed
                current_vc = member.guild.voice_client
                if current_vc and current_vc.channel:
                    current_human_members = [m for m in current_vc.channel.members if not m.bot]
                    if not current_human_members:
                        logger.info(f"Idle timeout reached for {current_vc.channel.name}. Leaving.")
                        # Send message to the last known text channel
                        player = self.players.get(member.guild.id)
                        if player and player._channel:
                             try:
                                 await player._channel.send("👋 Leaving voice channel due to inactivity.")
                             except discord.Forbidden:
                                 pass # Can't send message
                        await self.cleanup(member.guild)


    # --- Voice Connection Commands ---
    @commands.hybrid_command(name="join", aliases=['connect'], description="Join your voice channel or a specified one")
    async def join(self, ctx, *, channel: discord.VoiceChannel = None):
        """Joins a voice channel."""
        destination = channel or ctx.author.voice.channel if ctx.author.voice else None

        if not destination:
            return await ctx.send("You are not in a voice channel and didn't specify one.")

        if ctx.voice_client:
            if ctx.voice_client.channel == destination:
                 await ctx.send(f"Already connected to {destination.name}.")
                 return
            try:
                 await ctx.voice_client.move_to(destination)
                 await ctx.send(f"Moved to {destination.name}!")
            except asyncio.TimeoutError:
                 await ctx.send("Moving timed out, please try again.")
        else:
            try:
                await destination.connect(timeout=60.0, reconnect=True)
                await ctx.send(f"Joined {destination.name}!")
                # Ensure player exists after joining
                self.get_player(ctx)
            except asyncio.TimeoutError:
                 await ctx.send("Connecting timed out, please try again.")
            except discord.ClientException as e:
                 await ctx.send(f"Error connecting: {e}")


    @commands.hybrid_command(name="leave", aliases=['disconnect', 'dc'], description="Leave the voice channel")
    async def leave(self, ctx):
        """Leaves the voice channel and cleans up."""
        if not ctx.voice_client:
            return await ctx.send("I'm not connected to any voice channel.")

        await self.cleanup(ctx.guild) # Cleanup handles disconnect and player removal
        await ctx.send("Disconnected 👋")

    # --- Playback Control Commands ---
    @commands.hybrid_command(name="play", aliases=['p'], description="Play a song or add to queue (URL or search)")
    async def play(self, ctx, *, query: str):
        """Plays from URL or search query. Joins channel if needed."""
        await ctx.defer()

        # Ensure voice connection
        if not ctx.voice_client:
            if ctx.author.voice:
                try:
                    await ctx.author.voice.channel.connect(timeout=60.0, reconnect=True)
                except Exception as e:
                     return await ctx.send(f"Failed to join your channel: {e}")
            else:
                return await ctx.send("You need to be in a voice channel to play music.")

        # Ensure player exists
        player = self.get_player(ctx)
        was_empty = player.current is None and player.queue.empty()

        async with ctx.typing():
            try:
                source_info = await YTDLSource.create_source(query, loop=self.bot.loop, stream=True, requester=ctx.author)
                track = Track(source_info, ctx.author)
            except yt_dlp.utils.DownloadError as e:
                return await ctx.send(f"❌ Error fetching song: {e}")
            except Exception as e:
                 logger.error(f"Error creating source for '{query}': {e}", exc_info=True)
                 return await ctx.send(f"❌ An unexpected error occurred processing your request.")

            position = await player.add_track(track)

            # Send confirmation
            if not was_empty: # Don't send "Added" if it will play immediately
                embed = track.to_embed(embed_type="added")
                embed.set_footer(text=f"Position in queue: {position}")
                await ctx.send(embed=embed)
            else:
                # Acknowledge command, player loop will send Now Playing
                 await ctx.send(f"▶️ Playing **{track.title}** now.")


    @commands.hybrid_command(name="pause", description="Pause the current song")
    async def pause(self, ctx):
        """Pauses playback."""
        player = self.get_player(ctx)
        if player.is_playing():
            player.pause()
            await ctx.send("Playback paused ⏸️")
            await player.update_now_playing_message() # Update controls view
        else:
            await ctx.send("Nothing is playing.")

    @commands.hybrid_command(name="resume", description="Resume the paused song")
    async def resume(self, ctx):
        """Resumes playback."""
        player = self.get_player(ctx)
        if player.is_paused():
            player.resume()
            await ctx.send("Playback resumed ▶️")
            await player.update_now_playing_message() # Update controls view
        else:
            await ctx.send("Playback is not paused.")

    @commands.hybrid_command(name="skip", aliases=['s'], description="Skip the current song (vote or requester)")
    async def skip(self, ctx):
        """Skips the current song."""
        player = self.get_player(ctx)
        if not player.current:
            return await ctx.send("Nothing is playing to skip.")

        # Simple skip without voting via command
        # Voting logic could be added here if desired
        if ctx.author == player.current.requester or ctx.author.guild_permissions.manage_channels:
             player.skip()
             await ctx.send(f"⏭️ Song skipped by {ctx.author.mention}.")
        else:
             # Basic voting example (can be expanded)
             player.skip_votes.add(ctx.author.id)
             channel_members = [m for m in ctx.voice_client.channel.members if not m.bot]
             required = (len(channel_members) + 1) // 2 # Simple majority
             if len(player.skip_votes) >= required:
                 player.skip()
                 await ctx.send(f"⏭️ Skip vote passed! Skipping song.")
             else:
                 await ctx.send(f"🗳️ Skip vote added ({len(player.skip_votes)}/{required}).")


    @commands.hybrid_command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, ctx):
        """Stops playback and clears queue."""
        player = self.get_player(ctx)
        player.clear_queue()
        player.stop_current() # Stop ffmpeg
        await player.update_now_playing_message(clear_view=True) # Clear NP message
        await ctx.send("⏹️ Playback stopped and queue cleared.")


    @commands.hybrid_command(name="clear", aliases=['cq'], description="Clear the music queue")
    async def clear(self, ctx):
        """Clears the music queue."""
        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send("Queue is already empty.")

        player.clear_queue()
        await ctx.send("🗑️ Queue cleared.")

    # --- Queue Management Commands ---
    @commands.hybrid_command(name="queue", aliases=['q'], description="Show the music queue")
    async def queue(self, ctx, page: int = 1):
        """Displays the music queue."""
        player = self.get_player(ctx)
        queued_tracks = await player.get_tracks()

        if not player.current and not queued_tracks:
            return await ctx.send("Queue is empty.")

        items_per_page = 10
        pages = (len(queued_tracks) + items_per_page -1) // items_per_page if queued_tracks else 0
        if pages == 0 and player.current: pages = 1 # At least one page if something is playing
        if page < 1: page = 1
        if page > pages and pages > 0: page = pages

        embed = create_embed(title="🎵 Music Queue", color=discord.Color.blurple().value)
        embed.set_footer(text=f"Loop: {player.loop_mode} | Page {page}/{pages if pages > 0 else 1}")

        if player.current:
             current_pos, total_dur = player.get_progress()
             time_info = ""
             if total_dur > 0:
                  time_info = f" ({format_duration(current_pos)}/{format_duration(total_dur)})"
             elif player.current.duration == "LIVE":
                  time_info = " (LIVE)"

             embed.add_field(
                name="▶️ Now Playing",
                value=f"[{player.current.title}]({player.current.url}){time_info}\nRequested by: {player.current.requester.mention}",
                inline=False
             )

        if queued_tracks:
             start_index = (page - 1) * items_per_page
             end_index = start_index + items_per_page
             queue_list = []
             for i, track in enumerate(queued_tracks[start_index:end_index], start=start_index + 1):
                 queue_list.append(f"`{i}.` [{track.title}]({track.url}) `{track.duration}` | {track.requester.mention}")

             if queue_list:
                  embed.add_field(name=f"Up Next ({len(queued_tracks)} total)", value="\n".join(queue_list), inline=False)
             elif page > 1: # Show message if trying to access empty page > 1
                  embed.add_field(name="Up Next", value="No tracks on this page.", inline=False)


        await ctx.send(embed=embed)


    @commands.hybrid_command(name="nowplaying", aliases=['np'], description="Show the currently playing song and controls")
    async def nowplaying(self, ctx):
        """Shows the current song with progress and controls."""
        player = self.get_player(ctx)
        if not player.current:
            return await ctx.send("Nothing is playing right now.")

        # The player loop now handles sending/updating the message with controls.
        # This command can just resend the info or point to the message.
        # Let's resend the info embed for simplicity. Player loop manages the *persistent* one.
        temp_embed = player.current.to_embed(embed_type="now_playing")
        temp_embed.set_footer(text=f"Loop: {player.loop_mode} | Volume: {int(player.volume * 100)}%")

        current_pos, total_dur = player.get_progress()
        if total_dur > 0:
             progress_bar_text = create_progress_bar(current_pos, total_dur)
             time_info = f"{format_duration(current_pos)} / {format_duration(total_dur)}"
             temp_embed.add_field(name="Progress", value=f"{progress_bar_text} {time_info}", inline=False)
        elif player.current.duration == "LIVE":
             temp_embed.add_field(name="Progress", value="🔴 LIVE", inline=False)

        queue_size = player.queue.qsize()
        temp_embed.add_field(name="Queue", value=f"{queue_size} song(s) remaining", inline=True)

        await ctx.send(embed=temp_embed)
        # Optionally: If you want this command to also ensure the controls message exists:
        # await player.update_now_playing_message()


    @commands.hybrid_command(name="loop", description="Toggle loop mode (off, song, queue)")
    async def loop(self, ctx, mode: str = None):
        """Cycles or sets the loop mode."""
        player = self.get_player(ctx)
        new_mode = None
        msg = ""

        if mode is None: # Cycle modes
            if player.loop_mode == 'off': new_mode = 'song'
            elif player.loop_mode == 'song': new_mode = 'queue'
            else: new_mode = 'off'
        else:
            mode_lower = mode.lower()
            if mode_lower in ('off', 'none', 'disable'): new_mode = 'off'
            elif mode_lower in ('song', 'single', 'one', 'track'): new_mode = 'song'
            elif mode_lower in ('queue', 'all', 'playlist'): new_mode = 'queue'
            else:
                 return await ctx.send("Invalid mode. Use `off`, `song`, or `queue`.")

        player.loop_mode = new_mode
        if new_mode == 'off': msg = "➡️ Loop disabled."
        elif new_mode == 'song': msg = "🔂 Looping current song."
        elif new_mode == 'queue': msg = "🔁 Looping queue."

        await ctx.send(msg)
        await player.update_now_playing_message() # Update controls view


    @commands.hybrid_command(name="remove", aliases=['rm'], description="Remove a song from the queue by position")
    async def remove(self, ctx, position: int):
        """Removes a song from the queue by its position (1-based)."""
        player = self.get_player(ctx)
        if player.queue.empty():
            return await ctx.send("Queue is empty.")

        if position < 1 or position > player.queue.qsize():
            return await ctx.send(f"Invalid position. Must be between 1 and {player.queue.qsize()}.")

        # Adjust to 0-based index for removal
        removed_track = player.remove_track(position - 1)

        if removed_track:
            # Optional: Permission check (only requester or admin can remove)
            # if ctx.author != removed_track.requester and not ctx.author.guild_permissions.manage_channels:
            #     await player.add_track(removed_track) # Add it back
            #     return await ctx.send(f"You can only remove songs you requested (or need Manage Channels perm).")
            await ctx.send(f"🗑️ Removed **{removed_track.title}** from queue.")
        else:
             await ctx.send("❌ Failed to remove track (invalid index?).")


    @commands.hybrid_command(name="shuffle", description="Shuffle the music queue")
    async def shuffle(self, ctx):
        """Shuffles the tracks currently in the queue."""
        player = self.get_player(ctx)
        if player.shuffle_queue():
            await ctx.send("🔀 Queue shuffled!")
        else:
            await ctx.send("Not enough songs in the queue to shuffle (need > 1).")

    @commands.hybrid_command(name="seek", description="Seek to a time in the current song (e.g., 1:30, 90s)")
    async def seek(self, ctx, *, timestamp: str):
        """Seeks to a specific point in the current song."""
        player = self.get_player(ctx)
        if not player.current or player.current.duration == "LIVE":
            return await ctx.send("Not playing a seekable track right now.")

        seconds = 0
        try:
            time_parts = timestamp.replace('s', '').replace('m', ':').replace('h', ':').split(':')
            time_parts.reverse() # Process seconds first

            if len(time_parts) >= 1: seconds += int(time_parts[0])
            if len(time_parts) >= 2: seconds += int(time_parts[1]) * 60
            if len(time_parts) >= 3: seconds += int(time_parts[2]) * 3600

            if seconds < 0: raise ValueError("Time cannot be negative")
            if player.current.duration_seconds and seconds >= player.current.duration_seconds:
                 raise ValueError("Seek time exceeds track duration.")

        except (ValueError, TypeError):
             return await ctx.send("Invalid timestamp format. Use H:M:S, M:S, or seconds (e.g., `1:23:45`, `4:32`, `272s`).")

        await ctx.defer()
        success = await player.seek(seconds)

        if success:
            await ctx.send(f"⏩ Seeked to **{format_duration(seconds)}**.")
        else:
            await ctx.send("❌ Failed to seek the track.")


    @commands.hybrid_command(name="search", description="Search YouTube and choose a song to play")
    async def search(self, ctx, *, query: str):
        """Searches YouTube and lets the user pick a result."""
        await ctx.defer()

        try:
            results = await YTDLSource.search(query, loop=self.bot.loop, limit=5)
        except Exception as e:
             logger.error(f"Error during search for '{query}': {e}")
             return await ctx.send(f"❌ An error occurred during search: {e}")

        if not results:
            return await ctx.send(f"No results found for '{query}'.")

        embed = create_embed(
            title=f"🔎 Search Results for: `{query}`",
            description="Reply with the number of the song you want to play (e.g., `1`). Type `cancel` to abort.",
            color=discord.Color.dark_orange().value
        )

        results_text = []
        for i, entry in enumerate(results, 1):
            title = entry.get('title', 'Unknown Title')
            uploader = entry.get('uploader', 'Unknown')
            duration_sec = entry.get('duration')
            duration_str = format_duration(duration_sec) if duration_sec else "N/A"
            results_text.append(f"`{i}.` **{title}** `[{duration_str}]` (by {uploader})")

        embed.description += "\n\n" + "\n".join(results_text)

        search_msg = await ctx.send(embed=embed)

        def check(m):
             return m.author == ctx.author and m.channel == ctx.channel

        try:
            response_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
             await search_msg.edit(content="Search timed out.", embed=None, view=None)
             return
        finally:
             # Clean up the search message if possible
             try: await search_msg.delete()
             except: pass

        content = response_msg.content.strip()
        # Clean up user response too
        try: await response_msg.delete()
        except: pass

        if content.lower() == 'cancel':
            await ctx.send("Search cancelled.", delete_after=10)
            return

        try:
            choice = int(content)
            if not 1 <= choice <= len(results):
                raise ValueError
        except ValueError:
            await ctx.send("Invalid choice. Please enter a number from the list.", delete_after=10)
            return

        selected_entry = results[choice - 1]
        video_url = f"https://www.youtube.com/watch?v={selected_entry['id']}"

        # Use the play command to handle adding the selected track
        await self.play(ctx, query=video_url)


    # --- Error Handlers ---
    @play.error
    @seek.error
    @remove.error
    @queue.error
    # Add other command errors as needed
    async def voice_command_error(self, ctx, error):
        """Generic error handler for voice commands."""
        # Handle checks first
        if isinstance(error, commands.CheckFailure):
             # E.g., if you add a check that user must be in VC
             await ctx.send("You don't meet the requirements to use this command.")
        elif isinstance(error, commands.CommandInvokeError):
             original = error.original
             logger.error(f"Error invoking {ctx.command.name}: {original}", exc_info=original)
             await ctx.send(f"An error occurred: {original}")
        elif isinstance(error, commands.MissingRequiredArgument):
             await ctx.send(f"Missing argument: `{error.param.name}`. Use help for details.")
        elif isinstance(error, commands.BadArgument):
             await ctx.send(f"Invalid argument provided. Use help for details.")
        else:
             logger.error(f"Unhandled error in {ctx.command.name}: {error}", exc_info=error)
             await ctx.send("An unexpected error occurred.")

    @join.before_invoke
    @play.before_invoke
    # Add before_invoke for other commands needing voice
    async def ensure_voice_state(self, ctx):
        """Checks if the user is in a voice channel before certain commands."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("You are not connected to a voice channel.")

        # Optional: Check if bot has permissions to connect/speak
        permissions = ctx.author.voice.channel.permissions_for(ctx.me)
        if not permissions.connect or not permissions.speak:
             raise commands.CommandError("I don't have permission to connect or speak in your voice channel.")


async def setup(bot):
    await bot.add_cog(Voice(bot))