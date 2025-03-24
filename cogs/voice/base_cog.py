# cogs/voice/base_cog.py
"""
Base class for voice-related cogs with shared functionality and resources.
"""
import discord
from discord.ext import commands
import logging
from typing import Optional, Dict, Any

from utils.helpers import create_embed
from utils.player_ui import PlayerUIHelper
from utils.music_player import MusicPlayer
from utils.audio_effects import AudioEffectManager
from utils.music_queue import QueueManager

# Create singleton instances that will be shared across all voice cogs
_player_instance = None
_queue_manager_instance = None
_effect_manager_instance = None
_ui_helper_instance = None

def get_player():
    """Get the shared MusicPlayer instance"""
    global _player_instance
    if _player_instance is None:
        _player_instance = MusicPlayer()
        # Register after function to connect player with queue
        _player_instance.register_after_function(get_queue_manager().handle_track_finished)
    return _player_instance

def get_queue_manager():
    """Get the shared QueueManager instance"""
    global _queue_manager_instance
    if _queue_manager_instance is None:
        _queue_manager_instance = QueueManager(disconnect_timeout=300)
    return _queue_manager_instance

def get_effect_manager():
    """Get the shared AudioEffectManager instance"""
    global _effect_manager_instance
    if _effect_manager_instance is None:
        _effect_manager_instance = AudioEffectManager()
    return _effect_manager_instance

def get_ui_helper():
    """Get the shared PlayerUIHelper instance"""
    global _ui_helper_instance
    if _ui_helper_instance is None:
        _ui_helper_instance = PlayerUIHelper()
    return _ui_helper_instance


class BaseVoiceCog(commands.Cog):
    """Base class for voice-related cogs with shared functionality"""
    
    def __init__(self, bot):
        self.bot = bot
        self.player = get_player()
        self.queue_manager = get_queue_manager()
        self.effect_manager = get_effect_manager()
        self.ui_helper = get_ui_helper()
        
    async def ensure_voice_client(self, ctx):
        """Join the voice channel if not already connected"""
        voice_client = await self.player.join_voice_channel(ctx)
        if not voice_client:
            await ctx.send("You need to be in a voice channel first!")
            return None
        return voice_client
    
    async def update_playing_message(self, guild_id: int, track_data: Dict[str, Any]):
        """Update the now playing message with the current track"""
        try:
            if guild_id not in self.player.playing_messages:
                return
            
            message = self.player.playing_messages[guild_id]
            
            # Create embed with stream-aware information
            embed = create_embed(
                title=f"Now Playing ({track_data['platform']})",
                description=f"🎵 {track_data['title']}" + (" 📺 LIVE" if track_data['is_live'] else ""),
                color=discord.Color.purple().value if track_data['is_live'] else discord.Color.blue().value
            )
            
            # Add platform-specific fields
            if track_data['platform'] == 'Twitch':
                embed.add_field(
                    name="Streamer",
                    value=track_data['uploader'],
                    inline=True
                )
                if track_data.get('view_count'):
                    embed.add_field(
                        name="Viewers",
                        value=f"👁️ {track_data['view_count']:,}",
                        inline=True
                    )
            elif track_data['platform'] == 'SoundCloud':
                embed.add_field(
                    name="Artist",
                    value=track_data['uploader'],
                    inline=True
                )
                if track_data.get('like_count'):
                    embed.add_field(
                        name="Likes",
                        value=f"❤️ {track_data['like_count']:,}",
                        inline=True
                    )
            elif track_data['platform'] == 'YouTube':
                if track_data.get('uploader'):
                    embed.add_field(
                        name="Channel",
                        value=track_data['uploader'],
                        inline=True
                    )
                if track_data.get('view_count'):
                    embed.add_field(
                        name="Views",
                        value=f"👁️ {track_data['view_count']:,}",
                        inline=True
                    )

            # Add duration/progress bar only for non-live content
            if not track_data['is_live']:
                progress_bar = self.ui_helper.create_progress_bar(0, track_data['duration'])
                time_display = f"{self.ui_helper.format_time(0)} / {self.ui_helper.format_time(track_data['duration'])}"
                embed.add_field(
                    name="Duration",
                    value=f"{progress_bar}\n{time_display}",
                    inline=False
                )
            
            # Add queue position information
            queue_position = self.queue_manager.current_index.get(guild_id, 0) + 1
            queue_total = len(self.queue_manager.get_queue(guild_id))
            loop_mode = self.queue_manager.get_loop_mode(guild_id)
            
            loop_status = ""
            if loop_mode == 1:
                loop_status = " | 🔂 Looping Track"
            elif loop_mode == 2:
                loop_status = " | 🔁 Looping Queue"
            
            embed.add_field(
                name="Queue",
                value=f"Track {queue_position} of {queue_total}{loop_status}",
                inline=True
            )

            # Add format information
            footer_text = ""
            if track_data.get('format') and track_data['format'] != 'Unknown':
                footer_text += f"Format: {track_data['format']}"
            if track_data.get('quality') and track_data['quality'] != 'Unknown':
                if footer_text:
                    footer_text += " | "
                footer_text += f"Quality: {track_data['quality']}"
                
            # Add audio preset info if set
            quality_preset = self.effect_manager.get_quality_preset(guild_id)
            if quality_preset:
                if footer_text:
                    footer_text += " | "
                footer_text += f"Audio preset: {quality_preset}"
                
            if footer_text:
                embed.set_footer(text=footer_text)
            
            if track_data.get('thumbnail'):
                embed.set_thumbnail(url=track_data['thumbnail'])
            
            # Get appropriate view
            view = self.ui_helper.create_music_control_view(track_data['is_live'])
            
            # Update the message with the new embed and view
            await message.edit(embed=embed, view=view)
            
            # Start progress updates for non-live content
            if not track_data['is_live']:
                self.bot.loop.create_task(
                    self.player.start_progress_updates(
                        message, 
                        track_data,
                        self.ui_helper
                    )
                )
                
        except Exception as e:
            logging.error(f"Error updating playing message: {e}")