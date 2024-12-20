# cogs/voice.py
import discord
from discord.ext import commands
from discord.ui import Button, View
import yt_dlp
from typing import Dict, Optional
import asyncio
from utils.helpers import create_embed

# YT-DLP configuration
YTDLP_OPTIONS = {
    # Audio format selection
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio[ext=wav]/bestaudio/best',
    'prefer_free_formats': True,
    
    # Audio quality preferences
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'm4a',
        'preferredquality': '192',
    }],
    
    # Stream-specific settings
    'live_from_start': False,  # Start from current position for livestreams
    'wait_for_video': False,   # Don't wait for livestream to finish
    
    # Platform-specific settings
    'extract_flat': False,
    'writethumbnail': True,
    'no_playlist': True,
    
    # SoundCloud-specific settings
    'allow_playlist_files': False,
    'soundcloud_client_id': None,  # Will use internal client ID
    
    # Twitch-specific settings
    'twitch_disable_ads': True,    # Try to skip Twitch ads
    'twitch_skip_segments': True,
    
    # General settings
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    
    # Additional features
    'geo_bypass': True,
    'allow_unplayable_formats': False,
    'clean_infojson': False,
    'updatetime': False,
}

# Enhanced FFmpeg options for better audio quality
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k'  # Removed silenceremove as it can cause issues with seeking
}
# Specific FFmpeg options for livestreams
STREAM_FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        '-analyzeduration 12000000 -probesize 32000000'
    ),
    'options': (
        '-vn -b:a 160k '
        '-live_start_index -1 '  # Start from the latest segment
        '-fflags nobuffer '      # Reduce buffering
        '-flags low_delay '      # Minimize delay
        '-strict experimental'   # Allow experimental features
    )
}

def get_ffmpeg_options(self, is_live: bool, platform: str) -> dict:
        """Get appropriate FFmpeg options based on content type and platform"""
        if is_live:
            base_options = STREAM_FFMPEG_OPTIONS.copy()
            if platform == 'Twitch':
                # Additional Twitch-specific options
                base_options['before_options'] += (
                    ' -timeout 10000000'  # Longer timeout for Twitch
                )
                # Lower latency settings for Twitch
                base_options['options'] = (
                    '-vn -b:a 160k '
                    '-live_start_index -1 '
                    '-fflags nobuffer '
                    '-flags low_delay '
                    '-strict experimental '
                    '-avioflags direct'
                )
            return base_options
        else:
            return FFMPEG_OPTIONS.copy()
        
class MusicControlView(View):
    def __init__(self, voice_cog, is_live=False):
        super().__init__(timeout=None)  # Buttons won't timeout
        self.voice_cog = voice_cog
        
        # Add buttons
        self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏸️", custom_id="pause", label="Pause"))
        self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="▶️", custom_id="resume", label="Resume"))
        self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏹️", custom_id="stop", label="Stop"))
        if not is_live:
            self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏪", custom_id="rewind", label="-10s"))
            self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏩", custom_id="forward", label="+10s"))

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_states: Dict[int, discord.VoiceClient] = {}
        self.ytdlp = yt_dlp.YoutubeDL(YTDLP_OPTIONS)
        self.current_track: Dict[int, dict] = {}
        self.playing_messages: Dict[int, discord.Message] = {}

    def get_platform_name(self, url: str) -> str:
        """Identify the platform from the URL"""
        lower_url = url.lower()
        if 'youtube.com' in lower_url or 'youtu.be' in lower_url:
            return 'YouTube'
        elif 'soundcloud.com' in lower_url:
            return 'SoundCloud'
        elif 'twitch.tv' in lower_url:
            return 'Twitch'
        elif 'spotify.com' in lower_url:
            return 'Spotify'
        elif 'bandcamp.com' in lower_url:
            return 'Bandcamp'
        return 'Other'

    def create_progress_bar(self, current: float, total: float, length: int = 15) -> str:
        """Create a visual progress bar using Unicode blocks"""
        percentage = current / total
        filled_length = int(length * percentage)
        empty_length = length - filled_length
        
        bar = "▰" * filled_length + "▱" * empty_length
        return f"{bar} {int(percentage * 100)}%"

    def format_time(self, seconds: float) -> str:
        """Format seconds into MM:SS or HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    async def update_playing_message(self, message: discord.Message, track_data: dict):
        """Update the playing message with current progress"""
        try:
            embed = message.embeds[0]
            current_time = track_data['start_time']
            total_time = track_data['duration']
            
            # Update duration field with progress bar
            progress_bar = self.create_progress_bar(current_time, total_time)
            time_display = f"{self.format_time(current_time)} / {self.format_time(total_time)}"
            
            # Find and update the duration field
            for i, field in enumerate(embed.fields):
                if field.name == "Duration":
                    embed.set_field_at(
                        i,
                        name="Duration",
                        value=f"{progress_bar}\n{time_display}",
                        inline=False
                    )
                    break
            
            await message.edit(embed=embed)
            
        except discord.NotFound:
            # Message was deleted
            return
        except Exception as e:
            print(f"Error updating progress: {e}")
            return
        
    async def create_stream_player(self, voice_client: discord.VoiceClient, track_data: dict) -> None:
        """Create and set up the audio player with appropriate options"""
        try:
            # Get appropriate FFmpeg options
            ffmpeg_options = self.get_ffmpeg_options(
                track_data['is_live'],
                track_data['platform']
            )

            # For livestreams, we might need to refresh the URL
            if track_data['is_live']:
                try:
                    info = self.ytdlp.extract_info(track_data['url'], download=False)
                    if 'url' in info:
                        track_data['url'] = info['url']
                except Exception as e:
                    print(f"Error refreshing stream URL: {e}")

            # Create audio source
            audio_source = discord.FFmpegPCMAudio(
                track_data['url'],
                **ffmpeg_options
            )
            
            # Create transformer for volume control
            transformed_source = discord.PCMVolumeTransformer(audio_source, volume=1.0)
            
            # Play the audio
            voice_client.play(
                transformed_source,
                after=lambda e: print(f'Player error: {e}') if e else None
            )
            
        except Exception as e:
            print(f"Error creating stream player: {e}")
            raise e
        
    async def handle_stream_command(self, voice_client: discord.VoiceClient, 
                                  track_data: dict, command: str) -> bool:
        """Handle stream-specific commands (play, pause, resume)"""
        try:
            if command == "pause" and voice_client.is_playing():
                voice_client.pause()
                return True
            elif command == "resume" and voice_client.is_paused():
                voice_client.resume()
                return True
            elif command == "stop":
                voice_client.stop()
                return True
            elif command == "play":
                if voice_client.is_playing():
                    voice_client.stop()
                await self.create_stream_player(voice_client, track_data)
                return True
            return False
        except Exception as e:
            print(f"Error handling stream command: {e}")
            return False

    async def start_progress_updates(self, message: discord.Message, track_data: dict):
        """Start a task to update the progress bar periodically"""
        try:
            while self.get_voice_client(message) and self.get_voice_client(message).is_playing():
                await self.update_playing_message(message, track_data)
                track_data['start_time'] += 1
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Error in progress updates: {e}")
            return

    async def send_temporary_response(self, interaction: discord.Interaction, content: str, delete_after: float = 5.0):
        """Send an ephemeral message that deletes itself after a specified time"""
        await interaction.response.send_message(content, ephemeral=True)
        if delete_after > 0:
            await asyncio.sleep(delete_after)
            try:
                original_response = await interaction.original_response()
                await original_response.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

    def get_voice_client(self, ctx) -> Optional[discord.VoiceClient]:
        """Get the voice client for the current guild"""
        if isinstance(ctx, discord.Interaction):
            guild_id = ctx.guild_id
        else:
            guild_id = ctx.guild.id
        return self.voice_states.get(guild_id)

    async def join_voice_channel(self, ctx: commands.Context) -> Optional[discord.VoiceClient]:
        """Join the user's voice channel"""
        if ctx.author.voice is None:
            await ctx.send("You need to be in a voice channel first!")
            return None

        voice_channel = ctx.author.voice.channel
        voice_client = self.get_voice_client(ctx)

        if voice_client:
            if voice_client.channel.id != voice_channel.id:
                await voice_client.move_to(voice_channel)
            return voice_client

        voice_client = await voice_channel.connect()
        self.voice_states[ctx.guild.id] = voice_client
        return voice_client
    
    @commands.hybrid_command(name="join", description="Join your voice channel")
    async def join(self, ctx: commands.Context):
        """Join the user's voice channel"""
        await self.join_voice_channel(ctx)
        await ctx.send(f"Joined {ctx.author.voice.channel.name}")

    @commands.hybrid_command(name="leave", description="Leave the voice channel")
    async def leave(self, ctx: commands.Context):
        """Leave the voice channel"""
        voice_client = self.get_voice_client(ctx)
        if voice_client:
            await voice_client.disconnect()
            self.voice_states.pop(ctx.guild.id, None)
            self.current_track.pop(ctx.guild.id, None)
            await ctx.send("Left the voice channel")
        else:
            await ctx.send("I'm not in a voice channel")


    def get_track_info(self, url: str) -> dict:
        """Extract track information from URL with enhanced error handling"""
        try:
            # Update options based on platform
            platform = self.get_platform_name(url)
            options = YTDLP_OPTIONS.copy()

            if platform == 'Twitch':
                # Apply Twitch-specific optimizations
                options.update({
                    'format': 'audio_only/audio/best',
                    'live_from_start': False,
                })
            elif platform == 'SoundCloud':
                # Apply SoundCloud-specific optimizations
                options.update({
                    'format': 'bestaudio/best',
                    'preference_format': 'm4a',
                })

            self.ytdlp = yt_dlp.YoutubeDL(options)
            info = self.ytdlp.extract_info(url, download=False)
            
            if 'entries' in info:
                info = info['entries'][0]

            # Check if this is a livestream
            is_live = info.get('is_live', False)
            duration = None if is_live else info.get('duration', 0)

            return {
                'url': info['url'],
                'title': info['title'],
                'duration': duration,
                'thumbnail': info.get('thumbnail'),
                'platform': platform,
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'format': info.get('format', 'Unknown'),
                'quality': info.get('quality', 'Unknown'),
                'is_live': is_live
            }
        except Exception as e:
            raise commands.CommandError(f"Error extracting info: {str(e)}")

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks"""
        voice_client = self.get_voice_client(interaction)
        if not voice_client:
            await self.send_temporary_response(interaction, "Not connected to a voice channel!")
            return

        custom_id = interaction.data["custom_id"]
        track_data = self.current_track.get(interaction.guild_id)

        if not track_data:
            await self.send_temporary_response(interaction, "No track data available!")
            return
        
        try:
            if track_data.get('is_live'):
                # Handle livestream controls
                if custom_id == "pause":
                    success = await self.handle_stream_command(voice_client, track_data, "pause")
                    if success:
                        await self.send_temporary_response(interaction, "Stream paused ⏸️")
                    else:
                        await self.send_temporary_response(interaction, "Failed to pause stream")
                        
                elif custom_id == "resume":
                    success = await self.handle_stream_command(voice_client, track_data, "resume")
                    if success:
                        await self.send_temporary_response(interaction, "Stream resumed ▶️")
                    else:
                        await self.send_temporary_response(interaction, "Failed to resume stream")
                        
                elif custom_id == "stop":
                    success = await self.handle_stream_command(voice_client, track_data, "stop")
                    if success:
                        # Clean up
                        self.current_track.pop(interaction.guild_id, None)
                        self.voice_states.pop(interaction.guild_id, None)
                        await voice_client.disconnect()
                        
                        # Delete the now playing message
                        if interaction.guild_id in self.playing_messages:
                            try:
                                await self.playing_messages[interaction.guild_id].delete()
                                self.playing_messages.pop(interaction.guild_id)
                            except (discord.NotFound, discord.HTTPException):
                                pass
                        
                        await self.send_temporary_response(interaction, "Stream stopped and disconnected ⏹️")
                    else:
                        await self.send_temporary_response(interaction, "Failed to stop stream")
            else:
                if custom_id == "pause":
                    if voice_client.is_playing() and not voice_client.is_paused():
                        voice_client.pause()
                        await self.send_temporary_response(interaction, "Paused ⏸️")
                    else:
                        await self.send_temporary_response(interaction, "Nothing is playing!")
                        
                elif custom_id == "resume":
                    if voice_client.is_paused():
                        voice_client.resume()
                        await self.send_temporary_response(interaction, "Resumed ▶️")
                    else:
                        await self.send_temporary_response(interaction, "Not paused!")
                        
                elif custom_id == "stop":
                    if voice_client.is_playing() or voice_client.is_paused():
                        voice_client.stop()
                    
                    # Clean up
                    self.current_track.pop(interaction.guild_id, None)
                    self.voice_states.pop(interaction.guild_id, None)
                    
                    # Disconnect from voice
                    await voice_client.disconnect()
                    
                    # Delete the now playing message
                    if interaction.guild_id in self.playing_messages:
                        try:
                            await self.playing_messages[interaction.guild_id].delete()
                            self.playing_messages.pop(interaction.guild_id)
                        except (discord.NotFound, discord.HTTPException):
                            pass
                    
                    await self.send_temporary_response(interaction, "Stopped and left the channel ⏹️")
                        
                elif custom_id in ["forward", "rewind"]:
                    if not interaction.guild_id in self.current_track:
                        await self.send_temporary_response(interaction, "Nothing is playing!")
                        return
                        
                    track_data = self.current_track[interaction.guild_id]
                    current_time = track_data['start_time']
                    seek_time = current_time + 10 if custom_id == "forward" else current_time - 10
                    
                    seek_time = max(0, min(seek_time, track_data['duration']))
                    track_data['start_time'] = seek_time
                    
                    voice_client.stop()
                    
                    voice_client.play(
                        discord.FFmpegPCMAudio(
                            track_data['url'],
                            **{
                                **FFMPEG_OPTIONS,
                                'options': f'-vn -ss {seek_time}'
                            }
                        )
                    )
                    
                    direction = "Forward" if custom_id == "forward" else "Backward"
                    await self.send_temporary_response(
                        interaction,
                        f"{direction} 10s ({'%.1f' % seek_time}s / {track_data['duration']}s)"
                    )
        except Exception as e:
            await self.send_temporary_response(
                interaction,
                f"Error handling button click: {str(e)}",
                delete_after=10.0
            )

    @commands.hybrid_command(name="play", description="Play audio from a URL")
    async def play(self, ctx: commands.Context, *, url: str):
        """Play audio from URL with support for streams and regular content"""
        try:
            # Delete the user's message if it's a text command
            if not ctx.interaction:
                try:
                    await ctx.message.delete()
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    pass
            
            voice_client = await self.join_voice_channel(ctx)
            if not voice_client:
                return

            async with ctx.typing():
                track_info = self.get_track_info(url)
                
                # Create embed with stream-aware information
                embed = create_embed(
                    title=f"Now Playing ({track_info['platform']})",
                    description=f"🎵 {track_info['title']}" + (" 📺 LIVE" if track_info['is_live'] else ""),
                    color=discord.Color.purple().value if track_info['is_live'] else discord.Color.blue().value
                )
                
                # Add platform-specific fields
                if track_info['platform'] == 'Twitch':
                    embed.add_field(
                        name="Streamer",
                        value=track_info['uploader'],
                        inline=True
                    )
                    if track_info.get('view_count'):
                        embed.add_field(
                            name="Viewers",
                            value=f"👁️ {track_info['view_count']:,}",
                            inline=True
                        )
                elif track_info['platform'] == 'SoundCloud':
                    embed.add_field(
                        name="Artist",
                        value=track_info['uploader'],
                        inline=True
                    )
                    if track_info.get('like_count'):
                        embed.add_field(
                            name="Likes",
                            value=f"❤️ {track_info['like_count']:,}",
                            inline=True
                        )
                elif track_info['platform'] == 'YouTube':
                    if track_info.get('uploader'):
                        embed.add_field(
                            name="Channel",
                            value=track_info['uploader'],
                            inline=True
                        )
                    if track_info.get('view_count'):
                        embed.add_field(
                            name="Views",
                            value=f"👁️ {track_info['view_count']:,}",
                            inline=True
                        )

                # Add duration/progress bar only for non-live content
                if not track_info['is_live']:
                    progress_bar = self.create_progress_bar(0, track_info['duration'])
                    time_display = f"{self.format_time(0)} / {self.format_time(track_info['duration'])}"
                    embed.add_field(
                        name="Duration",
                        value=f"{progress_bar}\n{time_display}",
                        inline=False
                    )

                if track_info.get('format'):
                    embed.set_footer(text=f"Format: {track_info['format']} | Quality: {track_info['quality']}")
                
                if track_info.get('thumbnail'):
                    embed.set_thumbnail(url=track_info['thumbnail'])
                
                # Create view with appropriate controls
                view = MusicControlView(self, track_info['is_live'])
                
                self.current_track[ctx.guild.id] = {
                    'title': track_info['title'],
                    'url': track_info['url'],
                    'duration': track_info['duration'],
                    'start_time': 0,
                    'is_live': track_info['is_live'],
                    'platform': track_info['platform']
                }
                
                if voice_client.is_playing():
                    voice_client.stop()

                if ctx.guild.id in self.playing_messages:
                    try:
                        await self.playing_messages[ctx.guild.id].delete()
                    except (discord.errors.NotFound, discord.errors.Forbidden):
                        pass

                message = await ctx.send(embed=embed, view=view)
                self.playing_messages[ctx.guild.id] = message
                
                # Use different FFmpeg options for livestreams
                ffmpeg_options = FFMPEG_OPTIONS.copy()
                if track_info['is_live']:
                    ffmpeg_options['options'] = '-vn -b:a 160k'  # Lower bitrate for streams to prevent buffering
                else:
                    # Get appropriate bitrate based on platform
                    if track_info['platform'] == 'SoundCloud':
                        ffmpeg_options['options'] = '-vn -b:a 256k'  # Higher quality for SoundCloud
                    elif track_info['platform'] == 'YouTube':
                        ffmpeg_options['options'] = '-vn -b:a 192k'  # Standard quality for YouTube
                
                voice_client.play(
                    discord.FFmpegPCMAudio(
                        track_info['url'],
                        **ffmpeg_options
                    ),
                    after=lambda e: print(f'Player error: {e}') if e else None
                )
                
                # Only start progress updates for non-live content
                if not track_info['is_live']:
                    self.bot.loop.create_task(
                        self.start_progress_updates(message, self.current_track[ctx.guild.id])
                    )

        except Exception as e:
            error_embed = create_embed(
                title="Error Playing Track",
                description=str(e),
                color=discord.Color.red().value
            )
            await ctx.send(embed=error_embed)

    @commands.hybrid_command(name="seek", description="Skip to a specific position in seconds")
    async def seek(self, ctx: commands.Context, seconds: int):
        """Skip to a specific position in the track with improved handling"""
        try:
            voice_client = self.get_voice_client(ctx)
            if not voice_client:
                await ctx.send("Not connected to a voice channel!")
                return
                
            if not ctx.guild.id in self.current_track:
                await ctx.send("Nothing is playing!")
                return
            
            track_data = self.current_track[ctx.guild.id]
            if track_data.get('is_live'):
                await ctx.send("Cannot seek in livestreams!")
                return
            
            await ctx.defer()  # Defer the response for longer seeks
                
            track_data = self.current_track[ctx.guild.id]
            current_time = track_data['start_time']
            seek_time = current_time + seconds
            
            # Ensure seek_time is within valid bounds
            seek_time = max(0, min(seek_time, track_data['duration']))
            track_data['start_time'] = seek_time
            
            # For longer seeks or if we're far into the track, get a fresh URL
            if abs(seconds) > 60 or current_time > 600:  # 1 minute seek or 10 minutes into track
                try:
                    info = self.ytdlp.extract_info(track_data['url'], download=False)
                    if 'url' in info:
                        track_data['url'] = info['url']
                except Exception as e:
                    print(f"Error refreshing URL: {e}")
            
            # Stop current playback
            voice_client.stop()
            
            # Set up FFmpeg options with seek in before_options
            seek_options = {
                'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seek_time}',
                'options': FFMPEG_OPTIONS['options']
            }
            
            # Create and play new audio source
            audio_source = discord.FFmpegPCMAudio(
                track_data['url'],
                **seek_options
            )
            
            voice_client.play(
                audio_source,
                after=lambda e: print(f'Player error: {e}') if e else None
            )
            
            # Update progress display
            if ctx.guild.id in self.playing_messages:
                self.bot.loop.create_task(
                    self.start_progress_updates(
                        self.playing_messages[ctx.guild.id],
                        track_data
                    )
                )
            
            # Send confirmation with embed
            direction = "forward" if seconds > 0 else "backward"
            embed = create_embed(
                title="Position Updated",
                description=(
                    f"Seeked {direction} by {abs(seconds)}s\n"
                    f"Current position: {self.format_time(seek_time)} / "
                    f"{self.format_time(track_data['duration'])}"
                ),
                color=discord.Color.green().value
            )
            await ctx.send(embed=embed)
            
        except Exception as e:
            error_embed = create_embed(
                title="Error",
                description=f"Failed to seek: {str(e)}",
                color=discord.Color.red().value
            )
            await ctx.send(embed=error_embed)
            
            # Try to resume from previous position if seek fails
            try:
                if voice_client and track_data:
                    voice_client.play(
                        discord.FFmpegPCMAudio(
                            track_data['url'],
                            **{
                                'before_options': f'{FFMPEG_OPTIONS["before_options"]} -ss {current_time}',
                                'options': FFMPEG_OPTIONS['options']
                            }
                        )
                    )
            except Exception as resume_error:
                print(f"Error resuming playback: {resume_error}")

async def setup(bot):
    cog = Voice(bot)
    bot.add_listener(cog.on_button_click, "on_interaction")
    await bot.add_cog(cog)