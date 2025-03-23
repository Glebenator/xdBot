# utils/music_player.py
import discord
import yt_dlp
import asyncio
from typing import Dict, Optional, Any, List, Tuple
import logging
from utils.audio_constants import FFMPEG_OPTIONS, STREAM_FFMPEG_OPTIONS, YTDLP_OPTIONS

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
            raise Exception(f"Error extracting info: {str(e)}")
    
    async def create_stream_player(self, voice_client: discord.VoiceClient, track_data: dict, 
                                  ffmpeg_options: Optional[dict] = None) -> None:
        """Create and set up the audio player with appropriate options"""
        try:
            # Get appropriate FFmpeg options if not provided
            if not ffmpeg_options:
                if track_data['is_live']:
                    ffmpeg_options = STREAM_FFMPEG_OPTIONS.copy()
                    if track_data['platform'] == 'Twitch':
                        # Additional Twitch-specific options
                        ffmpeg_options['before_options'] += ' -timeout 10000000'
                        ffmpeg_options['options'] = (
                            '-vn -b:a 160k -live_start_index -1 -fflags nobuffer '
                            '-flags low_delay -strict experimental -avioflags direct'
                        )
                else:
                    ffmpeg_options = FFMPEG_OPTIONS.copy()

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
            print(f"Error in progress updates: {e}")
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
            print(f"Error updating progress: {e}")
            return