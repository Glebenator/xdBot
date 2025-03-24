# utils/music_player.py
import discord
import yt_dlp
import asyncio
from typing import Dict, Optional, Any, List, Tuple, Callable
import logging
from utils.audio_constants import (
    FFMPEG_OPTIONS, 
    STREAM_FFMPEG_OPTIONS, 
    PLATFORM_OPTIMIZATIONS,
    YTDLP_OPTIONS
)


class MusicPlayer:
    """Handles music extraction and playback"""
    
    def __init__(self):
        self.ytdlp = yt_dlp.YoutubeDL(YTDLP_OPTIONS)
        # Maps guild_id -> track_data
        self.current_track: Dict[int, Dict[str, Any]] = {}
        # Maps guild_id -> message
        self.playing_messages: Dict[int, discord.Message] = {}
        # Maps guild_id -> discord.VoiceClient
        self.voice_clients: Dict[int, discord.VoiceClient] = {}
        # After callbacks
        self._after_callbacks: List[Callable[[int, Optional[Exception]], None]] = []
        
    def register_after_function(self, callback: Callable[[int, Optional[Exception]], None]) -> None:
        """Register a callback to be called after a track finishes"""
        self._after_callbacks.append(callback)
        
    async def _call_after_functions(self, guild_id: int, error: Optional[Exception] = None) -> None:
        """Call all registered after functions"""
        for callback in self._after_callbacks:
            try:
                await callback(guild_id, error)
            except Exception as e:
                logging.error(f"Error in after callback: {e}")
        
    def get_voice_client(self, ctx_or_interaction) -> Optional[discord.VoiceClient]:
        """Get the voice client for the current guild"""
        if isinstance(ctx_or_interaction, discord.Interaction):
            guild_id = ctx_or_interaction.guild_id
        else:
            guild_id = ctx_or_interaction.guild.id
        return self.voice_clients.get(guild_id)
    
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
    
    async def join_voice_channel(self, ctx) -> Optional[discord.VoiceClient]:
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
        self.voice_clients[ctx.guild.id] = voice_client
        return voice_client
    
    def get_track_info(self, url: str) -> dict:
        """Extract track information from URL with enhanced error handling"""
        try:
            # Update options based on platform
            platform = self.get_platform_name(url)
            options = YTDLP_OPTIONS.copy()

            # Apply platform-specific optimizations
            if platform in PLATFORM_OPTIMIZATIONS:
                platform_opts = PLATFORM_OPTIMIZATIONS[platform]
                if 'format' in platform_opts:
                    options['format'] = platform_opts['format']
                if 'quality' in platform_opts:
                    options['quality'] = platform_opts['quality']

            self.ytdlp = yt_dlp.YoutubeDL(options)
            try:
                info = self.ytdlp.extract_info(url, download=False)
            except Exception as e:
                if 'YouTube' in platform:
                    # Try alternative YouTube extraction if initial attempt fails
                    logging.warning(f"First YouTube extraction attempt failed: {str(e)}. Trying alternative method...")
                    # Try with different format option
                    alt_options = options.copy()
                    alt_options['format'] = 'best'  # Fallback to simpler format selection
                    alt_options['youtube_include_dash_manifest'] = True  # Try with DASH manifest
                    self.ytdlp = yt_dlp.YoutubeDL(alt_options)
                    info = self.ytdlp.extract_info(url, download=False)
                else:
                    # Re-raise if not YouTube
                    raise
            
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
            
            # Check if we have a valid extracted info
            if not info or 'url' not in info or 'title' not in info:
                raise Exception(f"Could not extract video information from {url}")

            # Check if this is a livestream
            is_live = info.get('is_live', False)
            duration = None if is_live else info.get('duration', 0)

            # Safe handling of metadata
            view_count = info.get('view_count')
            like_count = info.get('like_count')
            
            # Make sure numeric values are properly handled
            if view_count is None:
                view_count = 0
            if like_count is None:
                like_count = 0
            
            # Extract format information safely
            formats = info.get('formats', [])
            best_format = None
            best_bitrate = 0
            
            for fmt in formats:
                # Look for audio-only formats with the highest bitrate
                if fmt and fmt.get('acodec') != 'none' and fmt.get('vcodec') in ('none', None):
                    # Safely handle bitrate information
                    abr = fmt.get('abr')
                    tbr = fmt.get('tbr')
                    
                    # Convert None to 0 for safe comparison
                    if abr is None:
                        abr = 0
                    if tbr is None:
                        tbr = 0
                        
                    bitrate = abr or tbr
                    
                    # Only compare if we have valid numeric bitrates
                    if isinstance(bitrate, (int, float)) and bitrate > best_bitrate:
                        best_bitrate = bitrate
                        best_format = fmt

            format_info = 'Unknown'
            quality_info = 'Unknown'
            
            if best_format:
                format_note = best_format.get('format_note')
                format_id = best_format.get('format_id')
                acodec = best_format.get('acodec', '')
                
                # Handle potentially missing format information
                if format_note:
                    format_info = format_note
                elif format_id:
                    format_info = format_id
                    
                # Safely handle bitrate information
                bitrate = best_format.get('abr') or best_format.get('tbr')
                
                if bitrate and isinstance(bitrate, (int, float)):
                    quality_info = f"{acodec} {bitrate}kbps"
                else:
                    quality_info = acodec
            
            # Fallback for direct audio URL if format extraction fails
            if not info.get('url'):
                logging.warning(f"Could not extract direct URL for {url}")
                info['url'] = url  # Use the original URL as fallback
            
            return {
                'url': info['url'],
                'title': info['title'],
                'duration': duration,
                'thumbnail': info.get('thumbnail'),
                'platform': platform,
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': view_count,
                'like_count': like_count,
                'format': format_info,
                'quality': quality_info,
                'is_live': is_live,
                'start_time': 0  # Add start_time for seeking
            }
        except Exception as e:
            logging.error(f"Error extracting info from {url}: {str(e)}")
            raise Exception(f"Error extracting info: {str(e)}")
    
    async def create_stream_player(self, voice_client: discord.VoiceClient, track_data: dict, 
                                  ffmpeg_options: Optional[dict] = None) -> None:
        """Create and set up the audio player with appropriate options"""
        if not voice_client or not voice_client.is_connected():
            logging.error("Voice client is not connected, cannot create stream player")
            return
            
        try:
            # Store guild_id for after function
            guild_id = voice_client.guild.id
            
            logging.info(f"[Guild {guild_id}] Creating stream player for: {track_data.get('title', 'Unknown')}")
            
            # Get appropriate FFmpeg options if not provided
            if not ffmpeg_options:
                if track_data.get('is_live', False):
                    ffmpeg_options = STREAM_FFMPEG_OPTIONS.copy()
                    
                    # Special handling for different platforms
                    platform = track_data.get('platform', 'Unknown')
                    logging.info(f"[Guild {guild_id}] Stream platform: {platform}")
                    
                    if platform == 'Twitch':
                        # Additional Twitch-specific options
                        ffmpeg_options['before_options'] += ' -timeout 10000000'
                        if 'Twitch' in PLATFORM_OPTIMIZATIONS:
                            twitch_opts = PLATFORM_OPTIMIZATIONS['Twitch']
                            if 'audio_options' in twitch_opts:
                                ffmpeg_options['options'] = twitch_opts['audio_options']
                else:
                    ffmpeg_options = FFMPEG_OPTIONS.copy()
                    # Apply platform-specific optimizations
                    platform = track_data.get('platform', 'Unknown')
                    logging.info(f"[Guild {guild_id}] Content platform: {platform}")
                    
                    if platform in PLATFORM_OPTIMIZATIONS:
                        platform_opts = PLATFORM_OPTIMIZATIONS[platform]
                        if 'audio_options' in platform_opts:
                            ffmpeg_options['options'] = platform_opts['audio_options']

            # For livestreams, we might need to refresh the URL
            if track_data.get('is_live', False):
                try:
                    logging.info(f"[Guild {guild_id}] Refreshing stream URL")
                    info = self.ytdlp.extract_info(track_data['url'], download=False)
                    if info and 'url' in info:
                        track_data['url'] = info['url']
                        logging.info(f"[Guild {guild_id}] Stream URL refreshed successfully")
                except Exception as e:
                    logging.error(f"Error refreshing stream URL: {e}")

            # Create audio source
            try:
                audio_source = discord.FFmpegPCMAudio(
                    track_data['url'],
                    **ffmpeg_options
                )
                
                # Create transformer for volume control
                transformed_source = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                
                # Update current track for the guild
                self.current_track[guild_id] = track_data
                
                # Define after callback within a function to ensure it's properly scoped
                def create_after_function():
                    async def after_callback(error):
                        if error:
                            logging.error(f"[Guild {guild_id}] Player error: {error}")
                        
                        logging.info(f"[Guild {guild_id}] Track ended, calling after functions")
                        try:
                            await self._call_after_functions(guild_id, error)
                        except Exception as e:
                            logging.error(f"Error in voice after callback: {e}")
                    
                    return lambda e: asyncio.run_coroutine_threadsafe(
                        after_callback(e), 
                        asyncio.get_event_loop()
                    )
                
                # Play the audio with properly scoped after function
                voice_client.play(
                    transformed_source,
                    after=create_after_function()
                )
                
                logging.info(f"[Guild {guild_id}] Started playback successfully")
                
            except Exception as source_error:
                logging.error(f"Error creating audio source: {source_error}")
                
                # Try with simpler options as a fallback
                try:
                    logging.info(f"[Guild {guild_id}] Trying fallback options")
                    simple_options = {
                        'before_options': '-reconnect 1 -reconnect_streamed 1',
                        'options': '-vn'
                    }
                    
                    audio_source = discord.FFmpegPCMAudio(
                        track_data['url'],
                        **simple_options
                    )
                    
                    transformed_source = discord.PCMVolumeTransformer(audio_source, volume=1.0)
                    self.current_track[guild_id] = track_data
                    
                    voice_client.play(
                        transformed_source,
                        after=lambda e: asyncio.run_coroutine_threadsafe(
                            self._call_after_functions(guild_id, e), 
                            asyncio.get_event_loop()
                        )
                    )
                    
                    logging.info(f"[Guild {guild_id}] Fallback playback successful")
                    
                except Exception as fallback_error:
                    logging.error(f"Fallback playback also failed: {fallback_error}")
                    raise fallback_error
                
        except Exception as e:
            logging.error(f"Error creating stream player: {e}")
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
            logging.error(f"Error handling stream command: {e}")
            return False
    
    async def start_progress_updates(self, message: discord.Message, track_data: dict, ui_helper):
        """Start a task to update the progress bar periodically"""
        # Get voice client from message's guild
        guild_id = message.guild.id
        voice_client = self.voice_clients.get(guild_id)
        
        try:
            while voice_client and voice_client.is_playing():
                await self.update_playing_message(message, track_data, ui_helper)
                track_data['start_time'] += 1
                await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"Error in progress updates: {e}")
            return
    
    async def update_playing_message(self, message: discord.Message, track_data: dict, ui_helper):
        """Update the playing message with current progress"""
        try:
            embed = message.embeds[0]
            current_time = track_data['start_time']
            total_time = track_data['duration']
            
            # Update duration field with progress bar
            progress_bar = ui_helper.create_progress_bar(current_time, total_time)
            time_display = f"{ui_helper.format_time(current_time)} / {ui_helper.format_time(total_time)}"
            
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
            logging.error(f"Error updating progress: {e}")
            return
            
    def cleanup_for_guild(self, guild_id: int):
        """Clean up resources for a guild"""
        # Remove voice client
        if guild_id in self.voice_clients:
            self.voice_clients.pop(guild_id, None)
        
        # Remove track data
        if guild_id in self.current_track:
            self.current_track.pop(guild_id, None)
        
        # Remove playing message
        if guild_id in self.playing_messages:
            self.playing_messages.pop(guild_id, None)

# Make sure to export the class at the end of the file
__all__ = ['MusicPlayer']