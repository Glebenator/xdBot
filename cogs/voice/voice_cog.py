# cogs/voice/voice_cog.py
"""Discord cog for voice and music playback functionality."""

import discord
from discord.ext import commands
import asyncio
import re
import logging
from utils.helpers import create_embed
from .player import MusicPlayer
from .track import Track
from .utils.ytdl import YTDLSource
from .utils.config import PLAYER_IDLE_TIMEOUT

# Setup logger
logger = logging.getLogger(__name__)

class Voice(commands.Cog):
    """Music playback commands for your Discord server."""

    def __init__(self, bot):
        """
        Initialize the Voice cog.
        
        Args:
            bot: Discord bot instance
        """
        self.bot = bot
        self.players = {}
        
    def get_player(self, ctx):
        """
        Retrieve the guild player, or generate one.
        
        Args:
            ctx: Command context
            
        Returns:
            MusicPlayer: Guild's music player
        """
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player

        return player

    async def cleanup(self, guild):
        """
        Cleanup the guild player.
        
        Args:
            guild: Guild to clean up
        """
        try:
            await guild.voice_client.disconnect()
        except AttributeError:
            pass

        try:
            del self.players[guild.id]
        except KeyError:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        Handle bot disconnection when left alone in voice channel.
        
        Args:
            member: Member whose voice state changed
            before: Previous voice state
            after: New voice state
        """
        # If the bot is in a voice channel and no other users are there, disconnect after timeout
        if member == self.bot.user and after.channel is None:
            # The bot was disconnected from the channel
            try:
                # Clean up the player
                await self.cleanup(member.guild)
            except Exception as e:
                logger.error(f"Error cleaning up player: {e}")
                
        # If the bot is in a voice channel and no other users are there
        if not member == self.bot.user and before.channel and self.bot.user in before.channel.members:
            # Check if the bot is alone in the voice channel
            if len([m for m in before.channel.members if not m.bot]) == 0:
                # Schedule disconnect after idle timeout of being alone
                await asyncio.sleep(PLAYER_IDLE_TIMEOUT)
                
                # Check again if still alone
                voice_client = member.guild.voice_client
                if voice_client and voice_client.channel and len([m for m in voice_client.channel.members if not m.bot]) == 0:
                    await self.cleanup(member.guild)
                    # Send message to the last text channel used
                    if member.guild.id in self.players:
                        player = self.players[member.guild.id]
                        await player._channel.send("Left voice channel due to inactivity.")

    @commands.hybrid_command(name="join", description="Join a voice channel")
    async def join(self, ctx, *, channel: discord.VoiceChannel = None):
        """
        Join the author's voice channel or a specified one.
        
        Args:
            ctx: Command context
            channel: Optional voice channel to join
        """
        if not channel and not ctx.author.voice:
            await ctx.send("You are not connected to a voice channel.")
            return

        destination = channel or ctx.author.voice.channel
        
        if ctx.voice_client:
            await ctx.voice_client.move_to(destination)
        else:
            ctx.voice_client = await destination.connect()

        await ctx.send(f"Joined {destination.name}!")

    @commands.hybrid_command(name="leave", description="Leave the voice channel")
    async def leave(self, ctx):
        """Leave the voice channel."""
        if not ctx.voice_client:
            await ctx.send("I am not connected to any voice channel.")
            return

        await self.cleanup(ctx.guild)
        await ctx.send("Disconnected from voice channel!")

    @commands.hybrid_command(name="play", description="Play a song from URL or search query")
    async def play(self, ctx, *, query):
        """
        Play a song from YouTube, SoundCloud, Spotify, or search query.
        
        Args:
            ctx: Command context
            query: URL or search query
        """
        await ctx.defer()  # Defer the response since this might take a while
        
        # Check if the bot is connected to a voice channel
        if not ctx.voice_client:
            # Try to join the author's voice channel
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                return

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(query, loop=self.bot.loop, requester=ctx.author)
                track = Track(source, ctx.author)
            except Exception as e:
                await ctx.send(f"An error occurred while processing your request: {str(e)}")
                logger.error(f"Error processing play command: {e}")
                return

            # Get the player for this guild
            player = self.get_player(ctx)
            
            # Add the track to the queue
            position = await player.add_track(track)
            
            # Only send the "Added to Queue" embed if the track isn't going to play immediately
            if player.current:
                # Create a nice embed
                embed = track.to_embed(embed_type="added")
                
                # Add position in queue
                embed.set_footer(text=f"Position in queue: {position}")
                
                await ctx.send(embed=embed)
            else:
                # If nothing is playing, the track will start immediately
                # Just acknowledge the command with a simple message
                await ctx.send("🎵 Starting playback...")

    @commands.hybrid_command(name="pause", description="Pause the currently playing song")
    async def pause(self, ctx):
        """
        Pause the currently playing song.
        
        Args:
            ctx: Command context
        """
        player = self.get_player(ctx)
        
        if not player.is_playing():
            await ctx.send("Nothing is playing right now.")
            return

        player.pause()
        await ctx.send("Music paused ⏸️")

    @commands.hybrid_command(name="resume", description="Resume the currently paused song")
    async def resume(self, ctx):
        """
        Resume the currently paused song.
        
        Args:
            ctx: Command context
        """
        player = self.get_player(ctx)
        
        if not player.is_paused():
            await ctx.send("Nothing is paused right now.")
            return

        player.resume()
        await ctx.send("Music resumed ▶️")

    @commands.hybrid_command(name="skip", description="Skip the currently playing song")
    async def skip(self, ctx):
        """
        Skip the currently playing song.
        
        Args:
            ctx: Command context
        """
        player = self.get_player(ctx)
        
        if not player.is_playing():
            await ctx.send("Nothing is playing right now.")
            return
        
        # Add the user to skip voters
        player.skip_votes.add(ctx.author.id)
        
        # Calculate votes required (half of non-bot users in voice channel)
        channel = ctx.voice_client.channel
        non_bots = [m for m in channel.members if not m.bot]
        required_votes = len(non_bots) // 2
        
        # If skip votes are enough or user is the requester, skip the song
        if len(player.skip_votes) >= required_votes or (player.current and player.current.requester == ctx.author):
            player.skip()
            await ctx.send("Song skipped ⏭️")
        else:
            # Not enough votes yet
            await ctx.send(f"Skip vote added! {len(player.skip_votes)}/{required_votes} votes required.")

    @commands.hybrid_command(name="queue", description="View the current song queue")
    async def queue(self, ctx):
        """
        View the music queue.
        
        Args:
            ctx: Command context
        """
        player = self.get_player(ctx)
        
        # Get tracks in queue
        upcoming = await player.get_tracks()
        
        if not upcoming and not player.current:
            await ctx.send("The queue is empty.")
            return

        # Create a nicely formatted queue embed
        embed = create_embed(
            title="Music Queue",
            description=f"Loop mode: {player.loop_mode}",
            color=discord.Color.blue().value
        )
        
        # Add current track
        if player.current:
            embed.add_field(
                name="Now Playing",
                value=f"[{player.current.title}]({player.current.url}) | Requested by: {player.current.requester.mention}",
                inline=False
            )

        if upcoming:
            queue_list = []
            for i, track in enumerate(upcoming, 1):
                if i <= 10:  # Only show first 10 tracks
                    queue_list.append(f"{i}. [{track.title}]({track.url}) | `{track.duration}` | Requested by: {track.requester.mention}")
            
            queue_text = "\n".join(queue_list)
            
            if len(upcoming) > 10:
                queue_text += f"\n... and {len(upcoming) - 10} more tracks"
            
            embed.add_field(name="Up Next", value=queue_text, inline=False)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="loop", description="Toggle loop mode: off, song, queue")
    async def loop(self, ctx, mode: str = None):
        """
        Change the loop mode: off, song, queue
        
        Args:
            ctx: Command context
            mode: Loop mode to set (off, song, queue)
        """
        player = self.get_player(ctx)
        
        # If no mode is specified, cycle through modes
        if mode is None:
            if player.loop_mode == 'off':
                player.loop_mode = 'song'
                await ctx.send("Loop mode set to: Single song 🔂")
            elif player.loop_mode == 'song':
                player.loop_mode = 'queue'
                await ctx.send("Loop mode set to: Queue 🔁")
            else:  # queue mode
                player.loop_mode = 'off'
                await ctx.send("Loop mode set to: Off ➡️")
            return
            
        # Otherwise, set to the specified mode
        mode = mode.lower()
        if mode in ('off', 'none', 'disable'):
            player.loop_mode = 'off'
            await ctx.send("Loop mode set to: Off ➡️")
        elif mode in ('song', 'single', 'one', 'track'):
            player.loop_mode = 'song'
            await ctx.send("Loop mode set to: Single song 🔂")
        elif mode in ('queue', 'all', 'playlist'):
            player.loop_mode = 'queue'
            await ctx.send("Loop mode set to: Queue 🔁")
        else:
            await ctx.send("Invalid loop mode. Use 'off', 'song', or 'queue'.")

    @commands.hybrid_command(name="nowplaying", description="Show information about the currently playing song")
    async def nowplaying(self, ctx):
        """
        Show information about the currently playing song.
        
        Args:
            ctx: Command context
        """
        player = self.get_player(ctx)
        
        if not player.current:
            await ctx.send("Nothing is playing right now.")
            return
            
        # Create now playing embed
        embed = player.current.to_embed(embed_type="now_playing")
        
        # Add loop status
        if player.loop_mode == 'song':
            embed.add_field(name="Loop Mode", value="Single song 🔂", inline=True)
        elif player.loop_mode == 'queue':
            embed.add_field(name="Loop Mode", value="Queue 🔁", inline=True)
        else:
            embed.add_field(name="Loop Mode", value="Off ➡️", inline=True)
            
        # Queue position
        queue_size = await player.get_tracks()
        embed.add_field(name="Queue", value=f"{len(queue_size)} song(s) in queue", inline=True)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="remove", description="Remove a song from the queue by its position")
    async def remove(self, ctx, index: int):
        """
        Remove a song from the queue by its index.
        
        Args:
            ctx: Command context
            index: Position in queue (1-based)
        """
        player = self.get_player(ctx)
        queue_size = len(await player.get_tracks())
        
        if queue_size == 0:
            await ctx.send("The queue is empty.")
            return
            
        if index < 1 or index > queue_size:
            await ctx.send(f"Index must be between 1 and {queue_size}.")
            return
            
        # Get the item to remove (adjust for 0-based indexing)
        removed_track = player.remove_track(index - 1)
        
        if removed_track:
            # Verify the requester
            if ctx.author != removed_track.requester and not ctx.author.guild_permissions.manage_channels:
                # Add the track back to the queue
                await player.add_track(removed_track)
                await ctx.send("You can only remove songs that you requested.")
                return
                
            await ctx.send(f"Removed from queue: **{removed_track.title}**")
        else:
            await ctx.send("Failed to remove the track.")

    @commands.hybrid_command(name="clear", description="Clear the music queue")
    async def clear(self, ctx):
        """
        Clear the music queue.
        
        Args:
            ctx: Command context
        """
        player = self.get_player(ctx)
        
        queue_size = len(await player.get_tracks())
        
        # Check if the queue is already empty
        if queue_size == 0:
            await ctx.send("The queue is already empty.")
            return
            
        # Clear the queue
        player.clear_queue()
        
        await ctx.send("Queue cleared ✅")

    @commands.hybrid_command(name="search", description="Search for a song on YouTube")
    async def search(self, ctx, *, query: str):
        """
        Search for songs on YouTube and display results for selection.
        
        Args:
            ctx: Command context
            query: Search query
        """
        await ctx.defer()
        
        # Search for videos
        results = await YTDLSource.search(query, loop=self.bot.loop)
        
        if not results:
            await ctx.send("No results found for your search.")
            return
            
        # Format the search results
        embed = create_embed(
            title=f"Search Results for: {query}",
            description="Select a song to play by typing its number, or type 'cancel' to cancel.",
            color=discord.Color.blue().value
        )
        
        for i, entry in enumerate(results, 1):
            title = entry.get('title', 'Unknown Title')
            uploader = entry.get('uploader', 'Unknown Uploader')
            duration = entry.get('duration')
            video_id = entry.get('id', '')
            
            if duration:
                minutes, seconds = divmod(duration, 60)
                duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = "Unknown"
                
            embed.add_field(
                name=f"{i}. {title}",
                value=f"Uploader: {uploader} | Duration: {duration_str}\n[Link](https://www.youtube.com/watch?v={video_id})",
                inline=False
            )
            
        # Send the search results
        search_message = await ctx.send(embed=embed)
        
        # Wait for user response
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and (
                m.content.isdigit() and 1 <= int(m.content) <= len(results) or 
                m.content.lower() == 'cancel'
            )
            
        try:
            response = await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await search_message.edit(content="Search timed out.", embed=None)
            return
            
        if response.content.lower() == 'cancel':
            await search_message.edit(content="Search cancelled.", embed=None)
            return
            
        # Get the selected entry
        selected_index = int(response.content) - 1
        selected_entry = results[selected_index]
        
        # Play the selected entry
        await ctx.invoke(self.play, query=f"https://www.youtube.com/watch?v={selected_entry['id']}")
        
        # Delete the search message and response for cleanliness
        try:
            await search_message.delete()
            await response.delete()
        except:
            pass

    @commands.hybrid_command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, ctx):
        """
        Stop playback and clear the queue.
        
        Args:
            ctx: Command context
        """
        player = self.get_player(ctx)
        
        # Clear the queue
        player.clear_queue()
        
        # Stop the current song
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            
        await ctx.send("Playback stopped and queue cleared ⏹️")

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Listen for direct mentions of the bot to play music.
        
        Args:
            message: Message to process
        """
        if message.author.bot or not message.guild:
            return
            
        # Check if the message starts with a mention of the bot
        if message.content.startswith(f'<@{self.bot.user.id}>') or message.content.startswith(f'<@!{self.bot.user.id}>'):
            # Extract the content after the mention
            content = message.content.split(' ', 1)
            if len(content) > 1:
                content = content[1].strip()
                
                # If message includes play or similar keywords
                if content.lower().startswith(('play ', 'p ')):
                    query = content.split(' ', 1)[1]
                    ctx = await self.bot.get_context(message)
                    await ctx.invoke(self.play, query=query)

    @play.before_invoke
    async def ensure_voice(self, ctx):
        """
        Ensure that the bot is in a voice channel before playing music.
        
        Args:
            ctx: Command context
            
        Raises:
            commands.CommandError: If the author is not in a voice channel
        """
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")