# cogs/voice.py
import discord
from discord.ext import commands
import asyncio
import re
from async_timeout import timeout
import yt_dlp as youtube_dl
import logging
from utils.helpers import create_embed
from typing import Optional, List, Dict, Any

# Setup logger
logger = logging.getLogger(__name__)

# URL validation patterns
URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»""'']))"
YOUTUBE_REGEX = r"^(https?\:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$"
SPOTIFY_REGEX = r"^(https?\:\/\/)?(open\.)?spotify\.com\/.+$"
SOUNDCLOUD_REGEX = r"^(https?\:\/\/)?(www\.)?(soundcloud\.com)\/.+$"

# YouTube DL options with high quality audio priority
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'opus',  # Opus format for better quality
    'audioquality': '0',  # Highest quality
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # Allow playlists
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'preferredcodec': 'opus',  # Prefer Opus codec for high quality
    'postprocessor_args': ['-ar', '48000', '-ac', '2'],  # 48kHz sampling, 2 channels
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -bufsize 3072k -ab 320k',  # Higher audio bitrate and buffer size
}

class YTDLSource:
    """Audio source from YouTube or other platforms using yt-dlp."""
    
    def __init__(self, source, *, data):
        self.source = source
        self.data = data
        self.title = data.get('title', 'Unknown title')
        self.url = data.get('webpage_url', 'Unknown URL')
        self.duration = self.parse_duration(data.get('duration'))
        self.thumbnail = data.get('thumbnail', 'https://via.placeholder.com/120')
        self.uploader = data.get('uploader', 'Unknown uploader')
        self.requester = None  # Will be set when song is requested

    @classmethod
    async def create_source(cls, search, *, loop=None, requester=None):
        """Create a source from a URL or search query."""
        loop = loop or asyncio.get_event_loop()
        ytdl = youtube_dl.YoutubeDL(YTDL_FORMAT_OPTIONS)

        # Process the search query
        if re.match(URL_REGEX, search):  # If it's a URL
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
                
                # Handle playlists
                if 'entries' in data:
                    # For playlists, return the first item
                    data = data['entries'][0]
            except Exception as e:
                logger.error(f"Error extracting info from URL: {e}")
                raise
        else:  # If it's a search query
            try:
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{search}", download=False))
                if 'entries' in data:
                    data = data['entries'][0]  # Take the first search result
            except Exception as e:
                logger.error(f"Error searching for query: {e}")
                raise

        filename = data['url']
        source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
        return cls(source, data=data)
        source.requester = requester
        return source

    @staticmethod
    def parse_duration(duration):
        """Convert duration in seconds to readable format."""
        if duration is None:
            return "LIVE"
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    @classmethod
    async def search(cls, search_query, *, loop=None, limit=5):
        """Search for videos matching the query."""
        loop = loop or asyncio.get_event_loop()
        ytdl = youtube_dl.YoutubeDL({
            **YTDL_FORMAT_OPTIONS,
            'extract_flat': True,  # Do not extract video info
        })
        
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch{limit}:{search_query}", download=False))
            if 'entries' in data:
                return data['entries']
            return []
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []


class MusicPlayer:
    """A class which manages the music queue and playback for a guild."""

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.current = None
        self.loop_mode = 'off'  # 'off', 'single', 'queue'
        self.skip_votes = set()  # Users who voted to skip

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Main player loop that handles playback of songs."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()
            self.skip_votes.clear()

            # Try to get the next song within 3 minutes.
            try:
                async with timeout(180):  # 3 minutes
                    if self.loop_mode == 'single' and self.current:
                        source = await YTDLSource.create_source(self.current.url, loop=self.bot.loop, requester=self.current.requester)
                    else:
                        source = await self.queue.get()
            except asyncio.TimeoutError:
                return self.destroy(self._guild)

            self.current = source

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            
            # Send a now playing message
            embed = create_embed(
                title="Now Playing",
                description=f"[{source.title}]({source.url})",
                color=discord.Color.green().value
            )
            embed.set_thumbnail(url=source.thumbnail)
            embed.add_field(name="Duration", value=source.duration, inline=True)
            embed.add_field(name="Requested by", value=source.requester.mention, inline=True)
            embed.add_field(name="Uploader", value=source.uploader, inline=True)
            embed.set_footer(text=f"Loop: {self.loop_mode}")
            
            await self._channel.send(embed=embed)
            await self.next.wait()

            # Make sure the FFmpeg process is cleaned up.
            source.cleanup()
            
            # If loop mode is 'queue', add the song back to the queue
            if self.loop_mode == 'queue':
                await self.queue.put(self.current)
            
            self.current = None

    def destroy(self, guild):
        """Disconnect and cleanup the player."""
        return self.bot.loop.create_task(self._cog.cleanup(guild))


class Voice(commands.Cog):
    """Music playback commands for your Discord server."""

    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        
    def get_player(self, ctx):
        """Retrieve the guild player, or generate one."""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = MusicPlayer(ctx)
            self.players[ctx.guild.id] = player

        return player

    async def cleanup(self, guild):
        """Cleanup the guild player."""
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
        """Handle bot disconnection when left alone in voice channel."""
        # If the bot is in a voice channel and no other users are there, disconnect after 2 minutes
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
                # Schedule disconnect after 2 minutes of being alone
                await asyncio.sleep(120)  # Wait 2 minutes
                
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
        """Join the author's voice channel or a specified one."""
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
        """Play a song from YouTube, SoundCloud, Spotify, or search query."""
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
                # Check if it's a Spotify URL
                if re.match(SPOTIFY_REGEX, query):
                    # For Spotify, extract the track/playlist name and search on YouTube
                    # This is a simple implementation - a real one would use Spotify API
                    spotify_parts = query.split('/')
                    search_query = spotify_parts[-1].split('?')[0]  # Extract ID
                    query = f"spotify track {search_query}"
                
                source = await YTDLSource.create_source(query, loop=self.bot.loop, requester=ctx.author)
            except Exception as e:
                await ctx.send(f"An error occurred while processing your request: {str(e)}")
                logger.error(f"Error processing play command: {e}")
                return

            # Get the player for this guild
            player = self.get_player(ctx)
            
            # Add the song to the queue
            await player.queue.put(source)
            
            # Create a nice embed
            embed = create_embed(
                title="Added to Queue",
                description=f"[{source.title}]({source.url})",
                color=discord.Color.blue().value
            )
            embed.set_thumbnail(url=source.thumbnail)
            embed.add_field(name="Duration", value=source.duration, inline=True)
            embed.add_field(name="Requested by", value=ctx.author.mention, inline=True)
            
            # Add position in queue
            position = player.queue.qsize()
            if player.current and position > 0:
                embed.set_footer(text=f"Position in queue: {position}")
            elif not player.current:
                embed.set_footer(text="Playing next")
            
            await ctx.send(embed=embed)

    @commands.hybrid_command(name="pause", description="Pause the currently playing song")
    async def pause(self, ctx):
        """Pause the currently playing song."""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing is playing right now.")
            return

        ctx.voice_client.pause()
        await ctx.send("Music paused ⏸️")

    @commands.hybrid_command(name="resume", description="Resume the currently paused song")
    async def resume(self, ctx):
        """Resume the currently paused song."""
        if not ctx.voice_client or not ctx.voice_client.is_paused():
            await ctx.send("Nothing is paused right now.")
            return

        ctx.voice_client.resume()
        await ctx.send("Music resumed ▶️")

    @commands.hybrid_command(name="skip", description="Skip the currently playing song")
    async def skip(self, ctx):
        """Skip the currently playing song."""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing is playing right now.")
            return

        # Get the player
        player = self.get_player(ctx)
        
        # Add the user to skip voters
        player.skip_votes.add(ctx.author.id)
        
        # Calculate votes required (half of non-bot users in voice channel)
        channel = ctx.voice_client.channel
        non_bots = [m for m in channel.members if not m.bot]
        required_votes = len(non_bots) // 2
        
        # If skip votes are enough or user is the requester, skip the song
        if len(player.skip_votes) >= required_votes or (player.current and player.current.requester == ctx.author):
            ctx.voice_client.stop()
            await ctx.send("Song skipped ⏭️")
        else:
            # Not enough votes yet
            await ctx.send(f"Skip vote added! {len(player.skip_votes)}/{required_votes} votes required.")

    @commands.hybrid_command(name="queue", description="View the current song queue")
    async def queue(self, ctx):
        """View the music queue."""
        player = self.get_player(ctx)
        
        if player.queue.empty() and not player.current:
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

        # Get queue items
        upcoming = list(player.queue._queue)
        
        if upcoming:
            queue_list = []
            for i, item in enumerate(upcoming, 1):
                if i <= 10:  # Only show first 10 tracks
                    queue_list.append(f"{i}. [{item.title}]({item.url}) | `{item.duration}` | Requested by: {item.requester.mention}")
            
            queue_text = "\n".join(queue_list)
            
            if len(upcoming) > 10:
                queue_text += f"\n... and {len(upcoming) - 10} more tracks"
            
            embed.add_field(name="Up Next", value=queue_text, inline=False)
        
        await ctx.send(embed=embed)

    # Volume command removed - Discord provides native volume controls for each user

    @commands.hybrid_command(name="loop", description="Toggle loop mode: off, song, queue")
    async def loop(self, ctx, mode: str = None):
        """Change the loop mode: off, song, queue"""
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
        """Show information about the currently playing song."""
        player = self.get_player(ctx)
        
        if not player.current:
            await ctx.send("Nothing is playing right now.")
            return
            
        source = player.current
        
        embed = create_embed(
            title="Now Playing",
            description=f"[{source.title}]({source.url})",
            color=discord.Color.green().value
        )
        embed.set_thumbnail(url=source.thumbnail)
        embed.add_field(name="Duration", value=source.duration, inline=True)
        embed.add_field(name="Requested by", value=source.requester.mention, inline=True)
        embed.add_field(name="Uploader", value=source.uploader, inline=True)
        
        # Loop status
        if player.loop_mode == 'song':
            embed.add_field(name="Loop Mode", value="Single song 🔂", inline=True)
        elif player.loop_mode == 'queue':
            embed.add_field(name="Loop Mode", value="Queue 🔁", inline=True)
        else:
            embed.add_field(name="Loop Mode", value="Off ➡️", inline=True)
            
        # Volume field removed - Using Discord's native volume controls
        
        # Queue position
        position = player.queue.qsize()
        embed.add_field(name="Queue", value=f"{position} song(s) in queue", inline=True)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="remove", description="Remove a song from the queue by its position")
    async def remove(self, ctx, index: int):
        """Remove a song from the queue by its index."""
        player = self.get_player(ctx)
        
        if player.queue.empty():
            await ctx.send("The queue is empty.")
            return
            
        if index < 1 or index > player.queue.qsize():
            await ctx.send(f"Index must be between 1 and {player.queue.qsize()}.")
            return
            
        # Get all items from the queue
        items = list(player.queue._queue)
        
        # Get the item to remove
        item_to_remove = items[index - 1]
        
        # Verify the requester
        if ctx.author != item_to_remove.requester and not ctx.author.guild_permissions.manage_channels:
            await ctx.send("You can only remove songs that you requested.")
            return
        
        # Clear the queue
        player.queue._queue.clear()
        
        # Add back all items except the one to remove
        for i, item in enumerate(items):
            if i != index - 1:
                await player.queue.put(item)
                
        await ctx.send(f"Removed from queue: **{item_to_remove.title}**")

    @commands.hybrid_command(name="clear", description="Clear the music queue")
    async def clear(self, ctx):
        """Clear the music queue."""
        player = self.get_player(ctx)
        
        # Check if the queue is already empty
        if player.queue.empty():
            await ctx.send("The queue is already empty.")
            return
            
        # Clear the queue
        player.queue._queue.clear()
        
        await ctx.send("Queue cleared ✅")

    @commands.hybrid_command(name="search", description="Search for a song on YouTube")
    async def search(self, ctx, *, query: str):
        """Search for songs on YouTube and display results for selection."""
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
        """Stop playback and clear the queue."""
        player = self.get_player(ctx)
        
        # Clear the queue
        player.queue._queue.clear()
        
        # Stop the current song
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            
        await ctx.send("Playback stopped and queue cleared ⏹️")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Listen for direct mentions of the bot to play music."""
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
        """Ensure that the bot is in a voice channel before playing music."""
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")

async def setup(bot):
    await bot.add_cog(Voice(bot))