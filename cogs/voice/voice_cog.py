# cogs/voice/voice_cog.py
import discord
from discord.ext import commands
import asyncio
import yt_dlp
import logging
import time
from utils.helpers import create_embed # Assuming you have this helper
from .player import MusicPlayer
from .track import Track
from .utils.ytdl import YTDLSource
# Removed: from .utils.config import PLAYER_IDLE_TIMEOUT # No longer needed
from .ui import PlayerControls

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def format_duration(seconds: int | float | str) -> str:
    """Formats seconds into M:SS or H:MM:SS. Handles 'LIVE'."""
    if isinstance(seconds, str) and seconds.upper() == "LIVE":
        return "LIVE"
    if seconds is None or not isinstance(seconds, (int, float)) or seconds <= 0:
        return "0:00"
    seconds = int(seconds) # Ensure integer for divmod
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def create_progress_bar(current: int | float, total: int | float | str, length: int = 15) -> str:
    """Creates a text-based progress bar. Handles 'LIVE' or unknown."""
    if isinstance(total, str) and total.upper() == "LIVE":
        return "`[🔴 LIVE ]`" + '─' * (length - len("[🔴 LIVE ]")) # Basic LIVE indicator
    if total is None or not isinstance(total, (int, float)) or total <= 0:
        return "`[ Unknown Duration ]`"

    current = int(current)
    total = int(total)
    percent = max(0.0, min(1.0, current / total)) # Clamp between 0 and 1
    filled_length = int(length * percent)
    bar = '█' * filled_length + '─' * (length - filled_length)
    return f"`[{bar}]`"

# --- Cog ---
class Voice(commands.Cog):
    """Music playback commands."""

    def __init__(self, bot):
        self.bot = bot
        self.players = {} # guild_id: MusicPlayer

    def get_player(self, ctx) -> MusicPlayer:
        """Retrieve or create the guild's MusicPlayer."""
        guild_id = ctx.guild.id
        player = self.players.get(guild_id)
        if player is None or player._destroyed: # Also recreate if destroyed
            logger.info(f"Creating new player for guild {guild_id}")
            player = MusicPlayer(ctx)
            self.players[guild_id] = player
        # Always update the channel context in case commands are used elsewhere
        player._channel = ctx.channel
        return player

    async def cleanup(self, guild: discord.Guild):
        """Cleanup player and disconnect. Called by player.destroy() or leave command."""
        guild_id = guild.id
        logger.info(f"Running cleanup for guild {guild_id}")

        # 1. Destroy the player object if it exists
        player = self.players.pop(guild_id, None) # Get player and remove from dict
        if player and not player._destroyed:
            logger.info(f"Cleanup initiated: Destroying player object for guild {guild_id}.")
            player.destroy() # This should cancel tasks and start NP cleanup
            # Wait briefly to allow destroy tasks to start? Optional.
            # await asyncio.sleep(0.1)
        elif player and player._destroyed:
             logger.info(f"Cleanup initiated: Player for guild {guild_id} already destroyed.")
        else:
            logger.info(f"Cleanup initiated: No active player found for guild {guild_id} to destroy.")

        # 2. Disconnect the voice client if connected
        try:
            vc = guild.voice_client
            if vc and vc.is_connected():
                 await vc.disconnect(force=True)
                 logger.info(f"Disconnected from voice in guild {guild_id} during cleanup.")
            elif vc:
                 logger.info(f"Voice client existed but was not connected in guild {guild_id} during cleanup.")
            # else: No voice client to disconnect

        except Exception as e:
             logger.error(f"Error disconnecting during cleanup for guild {guild_id}: {e}")


    # --- Listeners ---
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Handles cleanup ONLY if the bot itself is disconnected from a voice channel."""
        # Check if the state change is for the bot itself
        if member.id == self.bot.user.id:
            # Check if the bot was in a channel and now is not
            if before.channel is not None and after.channel is None:
                 logger.info(f"Bot disconnected from '{before.channel.name}' ({before.channel.guild.id}) detected via voice_state_update.")
                 # Ensure cleanup runs if the bot is disconnected externally (e.g., kicked)
                 await self.cleanup(before.channel.guild)
            return # No further checks needed for the bot's own state changes

        # --- IDLE TIMER LOGIC REMOVED ---
        # The previous logic checking for human_members and starting timers is gone.


    # --- Voice Connection Commands ---
    @commands.hybrid_command(name="join", aliases=['connect'], description="Join your voice channel or a specified one")
    async def join(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Joins a voice channel."""
        # Determine destination channel
        if channel:
            destination = channel
        elif ctx.author.voice and ctx.author.voice.channel:
            destination = ctx.author.voice.channel
        else:
            embed = create_embed(description="❌ You are not in a voice channel and didn't specify one.", color=discord.Color.red())
            return await ctx.send(embed=embed, ephemeral=True)

        # Check bot's current state
        current_vc = ctx.voice_client

        if current_vc:
            if current_vc.channel == destination:
                 embed = create_embed(description=f"✅ Already connected to {destination.mention}.", color=discord.Color.green())
                 await ctx.send(embed=embed)
            else: # Move to the new channel
                 try:
                      await current_vc.move_to(destination)
                      embed = create_embed(description=f"➡️ Moved to {destination.mention}!", color=discord.Color.blue())
                      await ctx.send(embed=embed)
                      self.get_player(ctx) # Ensure player context is updated
                 except asyncio.TimeoutError:
                      embed = create_embed(description="❌ Moving timed out, please try again.", color=discord.Color.red())
                      await ctx.send(embed=embed, ephemeral=True)
                 except Exception as e:
                      embed = create_embed(description=f"❌ Error moving: {e}", color=discord.Color.red())
                      await ctx.send(embed=embed, ephemeral=True)
        else: # Not connected, attempt to connect
            try:
                # Check permissions before connecting
                permissions = destination.permissions_for(ctx.me)
                if not permissions.connect:
                    embed = create_embed(description=f"❌ I don't have permission to **connect** to {destination.mention}.", color=discord.Color.red())
                    return await ctx.send(embed=embed, ephemeral=True)
                if not permissions.speak:
                    embed = create_embed(description=f"❌ I don't have permission to **speak** in {destination.mention}.", color=discord.Color.red())
                    return await ctx.send(embed=embed, ephemeral=True)

                await destination.connect(timeout=60.0, reconnect=True, self_deaf=True)
                embed = create_embed(description=f"✅ Joined {destination.mention}!", color=discord.Color.green())
                await ctx.send(embed=embed)
                # Ensure player exists after joining
                self.get_player(ctx)
            except asyncio.TimeoutError:
                 embed = create_embed(description="❌ Connecting timed out, please try again.", color=discord.Color.red())
                 await ctx.send(embed=embed, ephemeral=True)
            except discord.ClientException as e:
                 # Often occurs if already connecting/connected in another guild quickly
                 embed = create_embed(description=f"❌ Error connecting: {e}", color=discord.Color.red())
                 await ctx.send(embed=embed, ephemeral=True)
            except Exception as e:
                 logger.error(f"Unexpected error joining voice channel {destination.id}: {e}", exc_info=True)
                 embed = create_embed(description=f"❌ An unexpected error occurred while joining.", color=discord.Color.red())
                 await ctx.send(embed=embed, ephemeral=True)


    @commands.hybrid_command(name="leave", aliases=['disconnect', 'dc'], description="Leave the voice channel and clear queue")
    async def leave(self, ctx: commands.Context):
        """Leaves the voice channel and cleans up the player."""
        vc = ctx.voice_client
        if not vc or not vc.is_connected():
            embed = create_embed(description="❌ I'm not connected to any voice channel.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        # Call cleanup, which handles player destruction and disconnect
        await self.cleanup(ctx.guild)
        embed = create_embed(description="👋 Disconnected and cleared queue.", color=discord.Color.blue())
        await ctx.send(embed=embed)


    # --- Playback Control Commands ---
    @commands.hybrid_command(name="play", aliases=['p'], description="Play a song or add to queue (URL or search)")
    async def play(self, ctx: commands.Context, *, query: str):
        """Plays from URL or search query. Joins channel if needed."""
        await ctx.defer() # Acknowledge command quickly

        # Ensure user is in a voice channel
        if not ctx.author.voice or not ctx.author.voice.channel:
            embed = create_embed(description="❌ You need to be in a voice channel to play music.", color=discord.Color.red())
            return await ctx.followup.send(embed=embed, ephemeral=True)

        user_channel = ctx.author.voice.channel
        current_vc = ctx.voice_client

        # Connect if not connected
        if not current_vc:
            try:
                permissions = user_channel.permissions_for(ctx.me)
                if not permissions.connect or not permissions.speak:
                    embed = create_embed(description=f"❌ I need **connect** and **speak** permissions for {user_channel.mention}.", color=discord.Color.red())
                    return await ctx.followup.send(embed=embed, ephemeral=True)
                await user_channel.connect(timeout=60.0, reconnect=True, self_deaf=True)
                logger.info(f"Auto-joined {user_channel.name} for play command.")
                current_vc = ctx.voice_client # Update vc reference
            except Exception as e:
                 embed = create_embed(description=f"❌ Failed to join your channel '{user_channel.name}': {e}", color=discord.Color.red())
                 return await ctx.followup.send(embed=embed, ephemeral=True)
        # Check if user is in the same channel as the bot
        elif current_vc.channel != user_channel:
             embed = create_embed(description=f"❌ You must be in the same voice channel ({current_vc.channel.mention}) to play music.", color=discord.Color.red())
             return await ctx.followup.send(embed=embed, ephemeral=True)

        # Get player (will create if needed)
        player = self.get_player(ctx)
        was_empty = player.current is None and player.queue.empty()

        # Add track logic
        async with ctx.typing():
            try:
                # Check for playlist (basic heuristic)
                is_playlist = 'list=' in query or '/playlist/' in query

                if is_playlist:
                    # Inform user processing might take time
                    processing_msg = await ctx.followup.send(f"🔎 Processing playlist... this may take a moment.", wait=True) # Use wait=True

                    source_infos = await YTDLSource.create_playlist_source(query, loop=self.bot.loop, stream=True, requester=ctx.author)
                    if not source_infos:
                        raise ValueError("Could not extract any playable tracks from the playlist URL.")

                    tracks_added = 0
                    skipped_count = 0
                    for source_info in source_infos:
                        try:
                            track = Track(source_info, ctx.author)
                            await player.add_track(track)
                            tracks_added += 1
                        except Exception as e:
                            logger.warning(f"Skipping playlist item due to error: {e} (Query: {query}, Item Title: {source_info.get('title', 'N/A')})")
                            skipped_count += 1
                            continue # Skip problematic track

                    # Edit the processing message with results
                    if tracks_added > 0:
                        desc = f"✅ Added **{tracks_added}** songs from the playlist to the queue."
                        if skipped_count > 0:
                            desc += f" ({skipped_count} skipped due to errors)."
                        embed = create_embed(description=desc, color=discord.Color.green())
                        await processing_msg.edit(content=None, embed=embed)
                    else:
                        embed = create_embed(description="❌ No valid tracks were found or added from the playlist.", color=discord.Color.red())
                        await processing_msg.edit(content=None, embed=embed)

                else: # Single track
                    source_info = await YTDLSource.create_source(query, loop=self.bot.loop, stream=True, requester=ctx.author)
                    track = Track(source_info, ctx.author)
                    position = await player.add_track(track)

                    # Send confirmation
                    if not was_empty: # Don't send "Added" if it will play immediately
                        embed = track.to_embed(embed_type="added")
                        embed.set_footer(text=f"Position in queue: {position}")
                        await ctx.followup.send(embed=embed)
                    else:
                        # Let the player loop handle the Now Playing message for immediate play
                        await ctx.followup.send(f"▶️ Added **{track.title}** to the queue. Starting playback...")


            except yt_dlp.utils.DownloadError as e:
                 error_msg = str(e).split('ERROR: ')[-1] # Get cleaner error message
                 if "is not available" in error_msg: err_desc = "❌ Song not available (region lock, deleted, private?)."
                 elif "Unsupported URL" in error_msg: err_desc = "❌ The provided link is not a supported URL."
                 elif "Video unavailable" in error_msg: err_desc = "❌ Video unavailable."
                 else: err_desc = f"❌ Error fetching song details: {error_msg}"
                 embed = create_embed(description=err_desc, color=discord.Color.red())
                 # Use edit if processing_msg exists, else followup.send
                 if 'processing_msg' in locals() and processing_msg: await processing_msg.edit(content=None, embed=embed)
                 else: await ctx.followup.send(embed=embed, ephemeral=True)
            except ValueError as e: # Catch custom errors like empty playlist
                 embed = create_embed(description=f"❌ {e}", color=discord.Color.red())
                 if 'processing_msg' in locals() and processing_msg: await processing_msg.edit(content=None, embed=embed)
                 else: await ctx.followup.send(embed=embed, ephemeral=True)
            except Exception as e:
                 logger.error(f"Error creating source for '{query}': {e}", exc_info=True)
                 embed = create_embed(description=f"❌ An unexpected error occurred processing your request.", color=discord.Color.red())
                 if 'processing_msg' in locals() and processing_msg: await processing_msg.edit(content=None, embed=embed)
                 else: await ctx.followup.send(embed=embed, ephemeral=True)

    # --- Other commands remain largely the same as the previous full implementation ---
    # (pause, resume, skip, stop, clear, queue, nowplaying, loop, remove, shuffle, seek, search)
    # Make sure their error messages and player interactions are still correct.
    # Ensure they use self.players.get(ctx.guild.id) and handle None cases.

    @commands.hybrid_command(name="pause", description="Pause the current song")
    async def pause(self, ctx: commands.Context):
        """Pauses playback."""
        player = self.players.get(ctx.guild.id)
        if player and player.is_playing():
            player.pause()
            embed = create_embed(description="⏸️ Playback paused.", color=discord.Color.blue())
            await ctx.send(embed=embed)
            await player.update_now_playing_message() # Update controls view
        elif player and player.is_paused():
            embed = create_embed(description="⏸️ Playback is already paused.", color=discord.Color.orange())
            await ctx.send(embed=embed, ephemeral=True)
        else:
            embed = create_embed(description="❌ Nothing is playing or player not found.", color=discord.Color.orange())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="resume", description="Resume the paused song")
    async def resume(self, ctx: commands.Context):
        """Resumes playback."""
        player = self.players.get(ctx.guild.id)
        if player and player.is_paused():
            player.resume()
            embed = create_embed(description="▶️ Playback resumed.", color=discord.Color.blue())
            await ctx.send(embed=embed)
            await player.update_now_playing_message() # Update controls view
        elif player and player.is_playing():
             embed = create_embed(description="▶️ Playback is already playing.", color=discord.Color.orange())
             await ctx.send(embed=embed, ephemeral=True)
        else:
            embed = create_embed(description="❌ Playback is not paused or player not found.", color=discord.Color.orange())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="skip", aliases=['s'], description="Skip the current song (vote or requester/admin)")
    async def skip(self, ctx: commands.Context):
        """Skips the current song."""
        player = self.players.get(ctx.guild.id)
        if not player or not player.current:
            embed = create_embed(description="❌ Nothing is playing to skip.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        # Permission check: Requester or someone with Manage Channels can skip freely
        can_skip_freely = (ctx.author == player.current.requester or
                           ctx.author.guild_permissions.manage_channels)

        if can_skip_freely:
             player.skip() # This stops the VC, player loop handles the rest
             embed = create_embed(description=f"⏭️ Song skipped by {ctx.author.mention}.", color=discord.Color.blue())
             await ctx.send(embed=embed)
             # Player loop will update NP msg when next track starts or queue ends
        else:
             # Voting logic
             voter = ctx.author
             vc = ctx.voice_client
             if not vc or not vc.channel: # Should not happen if player.current exists, but check anyway
                 embed = create_embed(description="❌ Internal error: Voice client not found for voting.", color=discord.Color.red())
                 return await ctx.send(embed=embed, ephemeral=True)

             channel_members = [m for m in vc.channel.members if not m.bot]
             # Require votes from majority of human listeners (minimum 1)
             required = max(1, len(channel_members) // 2 + 1)

             if voter.id in player.skip_votes:
                 embed = create_embed(description=f"🗳️ You have already voted ({len(player.skip_votes)}/{required}).", color=discord.Color.orange())
                 await ctx.send(embed=embed, ephemeral=True, delete_after=15)
                 return

             player.skip_votes.add(voter.id)
             votes_needed = required - len(player.skip_votes)

             if votes_needed <= 0:
                 player.skip()
                 embed = create_embed(description=f"🗳️ Skip vote passed! ({len(player.skip_votes)}/{required}) Skipping song.", color=discord.Color.blue())
                 await ctx.send(embed=embed)
             else:
                 embed = create_embed(description=f"🗳️ Skip vote added by {voter.mention}. {votes_needed} more vote(s) needed ({len(player.skip_votes)}/{required}).", color=discord.Color.blue())
                 await ctx.send(embed=embed)


    @commands.hybrid_command(name="stop", description="Stop playback entirely and clear the queue")
    async def stop(self, ctx: commands.Context):
        """Stops playback, clears queue, and destroys the player instance for this guild."""
        player = self.players.get(ctx.guild.id)
        if not player:
            embed = create_embed(description="❌ Player is not active.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        # Optional: Permission Check (e.g., only admin/DJ)
        # if not ctx.author.guild_permissions.manage_guild:
        #     embed = create_embed(description="❌ You don't have permission to stop the player.", color=discord.Color.red())
        #     return await ctx.send(embed=embed, ephemeral=True)

        logger.info(f"Stop command issued by {ctx.author} in guild {ctx.guild.id}. Destroying player.")
        # Destroy the player instance - this handles clearing queue, stopping VC, cancelling loop
        player.destroy() # Calls cleanup internally if cog ref exists
        # cleanup should handle removing player from self.players dict

        embed = create_embed(description="⏹️ Playback stopped, queue cleared, and player resources released.", color=discord.Color.red())
        await ctx.send(embed=embed)


    @commands.hybrid_command(name="clear", aliases=['cq'], description="Clear all songs from the queue")
    async def clear(self, ctx: commands.Context):
        """Clears the music queue."""
        player = self.players.get(ctx.guild.id)
        if not player:
            embed = create_embed(description="❌ Player not active.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        if player.queue.empty():
             embed = create_embed(description="✅ Queue is already empty.", color=discord.Color.blue())
             return await ctx.send(embed=embed)

        count = player.queue.qsize()
        player.clear_queue()
        embed = create_embed(description=f"🗑️ Cleared **{count}** tracks from the queue.", color=discord.Color.blue())
        await ctx.send(embed=embed)
        await player.update_now_playing_message() # Update footer info if NP msg exists

    # --- Queue Management Commands (queue, nowplaying, loop, remove, shuffle, seek, search) ---
    # Assume these are implemented similarly to the previous full version,
    # ensuring they correctly use `self.players.get(ctx.guild.id)` and handle
    # the case where the player might be None. Example for 'queue':

    @commands.hybrid_command(name="queue", aliases=['q'], description="Show the music queue")
    async def queue(self, ctx: commands.Context, page: int = 1):
        """Displays the music queue."""
        player = self.players.get(ctx.guild.id)
        if not player:
            embed = create_embed(description="❌ No active player to show the queue for.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        queued_tracks = await player.get_tracks() # Use player method

        if not player.current and not queued_tracks:
            embed = create_embed(description="Queue is empty and nothing is playing.", color=discord.Color.blue())
            return await ctx.send(embed=embed)

        # --- Pagination and Embed Logic (Same as before) ---
        items_per_page = 10
        total_items = len(queued_tracks)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

        if not 1 <= page <= total_pages:
             embed = create_embed(description=f"❌ Invalid page number. Please choose between 1 and {total_pages}.", color=discord.Color.red())
             return await ctx.send(embed=embed, ephemeral=True)

        embed = discord.Embed(title="🎵 Music Queue", color=discord.Color.blurple())
        embed.set_footer(text=f"Loop: {player.loop_mode.capitalize()} | Volume: {int(player.volume * 100)}% | Page {page}/{total_pages}")

        # Current Track Info
        if player.current:
             current_pos, total_dur = player.get_progress()
             time_info = ""
             if player.current.duration == "LIVE": time_info = " (🔴 LIVE)"
             elif isinstance(total_dur, (int, float)) and total_dur > 0: time_info = f" ({format_duration(current_pos)}/{format_duration(total_dur)})"

             embed.add_field(
                name="▶️ Now Playing",
                value=f"[{player.current.title}]({player.current.url}){time_info}\nRequested by: {player.current.requester.mention}",
                inline=False
             )
        else:
             embed.add_field(name="▶️ Now Playing", value="Nothing is currently playing.", inline=False)

        # Queue List for the current page
        if queued_tracks:
             start_index = (page - 1) * items_per_page
             end_index = min(start_index + items_per_page, total_items)
             queue_list = []
             for i, track in enumerate(queued_tracks[start_index:end_index], start=start_index + 1):
                  duration_str = format_duration(track.duration_seconds or track.duration) # Use helper
                  queue_list.append(f"`{i}.` [{track.title}]({track.url}) `{duration_str}` | Req: {track.requester.mention}")

             if queue_list:
                  embed.add_field(name=f"📋 Up Next ({total_items} total)", value="\n".join(queue_list), inline=False)
             # No need for elif page > 1 because total_pages handles invalid page numbers now
        else:
             embed.add_field(name="📋 Up Next", value="The queue is empty.", inline=False)

        await ctx.send(embed=embed)


    @commands.hybrid_command(name="nowplaying", aliases=['np'], description="Show the currently playing song")
    async def nowplaying(self, ctx: commands.Context):
        """Shows the current song with progress."""
        player = self.players.get(ctx.guild.id)
        if not player or not player.current:
            embed = create_embed(description="❌ Nothing is playing right now.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        # Re-send the info as a temporary message
        temp_embed = player.current.to_embed(embed_type="now_playing")
        temp_embed.set_footer(text=f"Loop: {player.loop_mode.capitalize()} | Volume: {int(player.volume * 100)}% | Queue: {player.queue.qsize()} tracks")

        current_pos, total_dur = player.get_progress()
        progress_bar_text = create_progress_bar(current_pos, total_dur)

        if player.current.duration == "LIVE": time_info = "🔴 LIVE"
        elif isinstance(total_dur, (int, float)) and total_dur > 0: time_info = f"{format_duration(current_pos)} / {format_duration(total_dur)}"
        else: time_info = "`[Unknown Duration]`"

        temp_embed.add_field(name="Progress", value=f"{progress_bar_text}\n{time_info}", inline=False)

        await ctx.send(embed=temp_embed)
        # Optionally trigger the persistent message update
        # await player.update_now_playing_message()


    @commands.hybrid_command(name="loop", description="Toggle loop mode (off, song, queue)")
    async def loop(self, ctx: commands.Context, mode: str = None):
        """Cycles or sets the loop mode."""
        player = self.players.get(ctx.guild.id)
        if not player:
            embed = create_embed(description="❌ Player not active.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        new_mode = None
        if mode is None: # Cycle
            modes = ['off', 'song', 'queue']
            current_index = modes.index(player.loop_mode)
            new_mode = modes[(current_index + 1) % len(modes)]
        else: # Set specific mode
            mode_lower = mode.lower()
            if mode_lower in ('off', 'none', 'disable', 'stop', 'no'): new_mode = 'off'
            elif mode_lower in ('song', 'single', 'one', 'track', 'current'): new_mode = 'song'
            elif mode_lower in ('queue', 'all', 'playlist', 'q'): new_mode = 'queue'
            else:
                 embed = create_embed(description="❌ Invalid loop mode. Use `off`, `song`, or `queue` (or leave blank to cycle).", color=discord.Color.red())
                 return await ctx.send(embed=embed, ephemeral=True)

        player.loop_mode = new_mode
        msg = f"➡️ Loop set to **{new_mode.capitalize()}**."
        if new_mode == 'song': msg = f"🔂 Looping current song."
        elif new_mode == 'queue': msg = f"🔁 Looping queue."

        embed = create_embed(description=msg, color=discord.Color.blue())
        await ctx.send(embed=embed)
        await player.update_now_playing_message() # Update footer/view

    @commands.hybrid_command(name="remove", aliases=['rm'], description="Remove a song from the queue by position")
    async def remove(self, ctx: commands.Context, position: int):
        """Removes a song from the queue by its position (1-based)."""
        player = self.players.get(ctx.guild.id)
        if not player:
            embed = create_embed(description="❌ Player not active.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        qsize = player.queue.qsize()
        if qsize == 0:
             embed = create_embed(description="❌ Queue is empty.", color=discord.Color.orange())
             return await ctx.send(embed=embed, ephemeral=True)

        if not 1 <= position <= qsize:
            embed = create_embed(description=f"❌ Invalid position. Must be between 1 and {qsize}.", color=discord.Color.red())
            return await ctx.send(embed=embed, ephemeral=True)

        # Adjust to 0-based index for removal logic
        removed_track = player.remove_track(position - 1) # Use player method

        if removed_track:
            # Optional: Permission check
            # if ctx.author != removed_track.requester and not ctx.author.guild_permissions.manage_channels: ...

            embed = create_embed(description=f"🗑️ Removed **{removed_track.title}** (position {position}) from queue.", color=discord.Color.blue())
            await ctx.send(embed=embed)
            await player.update_now_playing_message() # Update queue count in footer
        else:
             # Should be rare if index validation is correct
             embed = create_embed(description=f"❌ Failed to remove track at position {position}.", color=discord.Color.red())
             await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="shuffle", description="Shuffle the music queue")
    async def shuffle(self, ctx: commands.Context):
        """Shuffles the tracks currently in the queue."""
        player = self.players.get(ctx.guild.id)
        if not player:
            embed = create_embed(description="❌ Player not active.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        if player.shuffle_queue(): # Use player method
            embed = create_embed(description="🔀 Queue shuffled!", color=discord.Color.blue())
            await ctx.send(embed=embed)
            # No need to update NP message unless you show queue order there
        else:
            embed = create_embed(description="❌ Not enough songs in the queue to shuffle (need at least 2).", color=discord.Color.orange())
            await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="seek", description="Seek to a time in the current song (e.g., 1m30s, 90)")
    async def seek(self, ctx: commands.Context, *, timestamp: str):
        """Seeks to a specific point in the current song."""
        player = self.players.get(ctx.guild.id)
        if not player or not player.current:
            embed = create_embed(description="❌ Not playing anything.", color=discord.Color.orange())
            return await ctx.send(embed=embed, ephemeral=True)

        if player.current.duration == "LIVE":
             embed = create_embed(description="❌ Cannot seek in a live stream.", color=discord.Color.red())
             return await ctx.send(embed=embed, ephemeral=True)

        if not player.current.duration_seconds or player.current.duration_seconds <= 0:
             embed = create_embed(description="❌ Cannot seek: track duration unknown or invalid.", color=discord.Color.red())
             return await ctx.send(embed=embed, ephemeral=True)

        seconds = 0
        try:
            # Simple parser for H:M:S, M:S, S
            parts = timestamp.strip().replace('s', '').replace('m', ':').replace('h', ':').split(':')
            parts = [int(p.strip()) for p in parts if p.strip().isdigit()]
            if len(parts) == 1: seconds = parts[0]
            elif len(parts) == 2: seconds = parts[0] * 60 + parts[1]
            elif len(parts) == 3: seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
            else: raise ValueError("Invalid format")

            if seconds < 0: raise ValueError("Time cannot be negative")
            # Allow seeking slightly beyond duration? Maybe clamp instead.
            seconds = min(seconds, player.current.duration_seconds)

        except (ValueError, TypeError, IndexError):
             embed = create_embed(description="❌ Invalid timestamp. Use seconds (e.g., `90`), `M:S` (`1:30`), or `H:M:S` (`1:05:20`).", color=discord.Color.red())
             return await ctx.send(embed=embed, ephemeral=True)

        await ctx.defer()
        success = await player.seek(seconds) # Use player method

        if success:
            embed = create_embed(description=f"⏩ Seeked to **{format_duration(seconds)}**.", color=discord.Color.blue())
            await ctx.followup.send(embed=embed)
        else:
            embed = create_embed(description="❌ Failed to seek the track (maybe it ended or an error occurred?).", color=discord.Color.red())
            await ctx.followup.send(embed=embed, ephemeral=True)


    @commands.hybrid_command(name="search", description="Search YouTube and choose a song to play")
    async def search(self, ctx: commands.Context, *, query: str):
        """Searches YouTube and lets the user pick a result."""
        await ctx.defer()

        # Ensure user is in a VC for the subsequent play action
        if not ctx.author.voice or not ctx.author.voice.channel:
             embed = create_embed(description="❌ You must be in a voice channel to search and play music.", color=discord.Color.red())
             return await ctx.followup.send(embed=embed, ephemeral=True)

        try:
            results = await YTDLSource.search(query, loop=self.bot.loop, limit=5)
        except Exception as e:
             logger.error(f"Error during search for '{query}': {e}", exc_info=True)
             embed = create_embed(description=f"❌ An error occurred during search: {e}", color=discord.Color.red())
             return await ctx.followup.send(embed=embed, ephemeral=True)

        if not results:
            embed = create_embed(description=f"❌ No results found for '{query}'.", color=discord.Color.orange())
            return await ctx.followup.send(embed=embed, ephemeral=True)

        # Format results
        results_text = []
        for i, entry in enumerate(results, 1):
            title = entry.get('title', 'Unknown Title')
            uploader = entry.get('uploader', 'Unknown Artist')
            duration_str = format_duration(entry.get('duration'))
            results_text.append(f"`{i}.` **{title}** `[{duration_str}]`\n   _by {uploader}_")

        embed = discord.Embed(
            title=f"🔎 Search Results for: `{query}`",
            description="Reply with the number of the song you want to play (e.g., `1`). Type `cancel` to abort.\n\n" + "\n".join(results_text),
            color=discord.Color.dark_orange()
        )
        embed.set_footer(text="Search will time out in 60 seconds.")

        search_msg = await ctx.followup.send(embed=embed, wait=True) # Use wait=True

        def check(m: discord.Message):
             return m.author == ctx.author and m.channel == ctx.channel

        try:
            response_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
             try: await search_msg.edit(content="Search timed out.", embed=None, view=None)
             except discord.NotFound: pass
             return

        content = response_msg.content.strip()
        try: await response_msg.delete() # Delete user's number/cancel message
        except: pass

        if content.lower() == 'cancel':
            await search_msg.edit(content="Search cancelled.", embed=None, view=None, delete_after=10)
            return

        try:
            choice = int(content)
            if not 1 <= choice <= len(results): raise ValueError("Choice out of range")
        except ValueError:
            await search_msg.edit(content="Invalid choice. Please enter a number from the list.", embed=None, view=None, delete_after=10)
            return

        # Choice is valid, delete the search results message
        try: await search_msg.delete()
        except: pass

        selected_entry = results[choice - 1]
        video_url = selected_entry.get('webpage_url') or f"https://www.youtube.com/watch?v={selected_entry['id']}"
        title = selected_entry.get('title', 'Selected Video')

        # Invoke the play command to handle the logic
        play_command = self.bot.get_command('play')
        if play_command:
             logger.info(f"Invoking play command from search with URL: {video_url}")
             # We already deferred, so direct call should work if play handles followup
             # Need to ensure the context is suitable for followup if play defers again
             # Simpler: Call the coroutine directly
             await self.play(ctx, query=video_url)
             # Or, if play doesn't handle followup well from invoke:
             # await ctx.send(f"Adding '{title}' to queue...", delete_after=5) # Temp message
             # await self.play_coro(ctx, video_url) # Assuming play logic is in a coro
        else:
             logger.error("Could not find 'play' command to invoke from 'search'")
             await ctx.send(f"Selected '{title}'. Please use `/play {video_url}` manually.", delete_after=20)


    # --- Error Handlers ---
    # Keep the cog_command_error handler as before
    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # ... (Error handling logic from previous full implementation) ...
        # Make sure ephemeral=True is used appropriately for user errors
        if isinstance(error, commands.CheckFailure):
            if isinstance(error, commands.CommandError) and str(error) != "": # Custom errors from ensure_voice_state
                embed = create_embed(description=f"❌ {error}", color=discord.Color.red())
                await ctx.send(embed=embed, ephemeral=True)
            else:
                embed = create_embed(description="❌ You don't meet the requirements (e.g., not in VC / wrong VC).", color=discord.Color.red())
                await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.CommandNotFound): pass # Ignore
        elif isinstance(error, commands.MissingRequiredArgument):
             param_name = error.param.name
             embed = create_embed(description=f"❌ Missing argument: `{param_name}`. Use `/help {ctx.command.qualified_name}`.", color=discord.Color.orange())
             await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.BadArgument):
             embed = create_embed(description=f"❌ Invalid argument: {error}", color=discord.Color.orange())
             await ctx.send(embed=embed, ephemeral=True)
        elif isinstance(error, commands.CommandInvokeError):
             original = error.original
             logger.error(f"Error invoking '{ctx.command.qualified_name}': {original}", exc_info=original)
             if isinstance(original, yt_dlp.utils.DownloadError): user_msg = "❌ Failed to process track (unavailable, private?)."
             elif isinstance(original, discord.ClientException): user_msg = f"❌ Discord client error: {original}"
             else: user_msg = "🔧 An unexpected error occurred."
             embed = create_embed(description=user_msg, color=discord.Color.dark_red())
             send_method = ctx.followup.send if ctx.interaction and ctx.interaction.response.is_done() else ctx.send
             try: await send_method(embed=embed, ephemeral=True)
             except discord.NotFound: await ctx.channel.send(embed=embed) # Fallback
             except discord.InteractionResponded: await ctx.channel.send(embed=embed) # Fallback if followup fails
        elif isinstance(error, commands.CommandOnCooldown):
             embed = create_embed(description=f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s.", color=discord.Color.yellow())
             await ctx.send(embed=embed, ephemeral=True, delete_after=error.retry_after)
        else:
             logger.error(f"Unhandled error in '{ctx.command.qualified_name}': {error}", exc_info=error)
             embed = create_embed(description="🔧 An unknown error occurred.", color=discord.Color.dark_red())
             send_method = ctx.followup.send if ctx.interaction and ctx.interaction.response.is_done() else ctx.send
             try: await send_method(embed=embed, ephemeral=True)
             except discord.NotFound: await ctx.channel.send(embed=embed)
             except discord.InteractionResponded: await ctx.channel.send(embed=embed)


    # Apply before_invoke checks
    @pause.before_invoke
    @resume.before_invoke
    @skip.before_invoke
    @stop.before_invoke
    @clear.before_invoke
    @queue.before_invoke
    @nowplaying.before_invoke
    @loop.before_invoke
    @remove.before_invoke
    @shuffle.before_invoke
    @seek.before_invoke
    async def ensure_voice_state(self, ctx: commands.Context):
        """Checks voice state compatibility for commands."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError("You are not connected to a voice channel.")
        if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
            raise commands.CommandError(f"You must be in the same voice channel ({ctx.voice_client.channel.mention}).")
        # No need to check permissions here as most commands assume connection exists


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
    logger.info("Voice Cog loaded (Inactivity disconnect logic removed).")