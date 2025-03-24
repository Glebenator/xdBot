# cogs/voice/player_cog.py
"""
Main music player functionality for Discord bot.
Handles basic playback commands and interactions.
"""
import discord
from discord.ext import commands
import logging
from typing import Optional

from .base_cog import BaseVoiceCog
from .button_handlers import ButtonHandler
from utils.helpers import create_embed
from utils.player_ui import MusicControlView


class MusicPlayer(BaseVoiceCog):
    """Music player commands for the bot"""
    
    def __init__(self, bot):
        super().__init__(bot)
        # Register callbacks
        self.queue_manager.register_track_start_callback(self.on_track_start)
        self.queue_manager.register_track_end_callback(self.on_track_end)
        
    # === Callback Methods ===
    
    async def on_track_start(self, guild_id: int, track_data):
        """Called when a track starts playing"""
        try:
            # Update the now playing message for the track
            await self.update_playing_message(guild_id, track_data)
        except Exception as e:
            logging.error(f"Error in on_track_start: {e}")
    
    async def on_track_end(self, guild_id: int, track_data):
        """Called when a track ends playing"""
        try:
            # Any cleanup needed when a track ends
            pass
        except Exception as e:
            logging.error(f"Error in on_track_end: {e}")
    
    # === Button Handling ===
    
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle button interactions"""
        if interaction.type != discord.InteractionType.component:
            return
            
        await ButtonHandler.handle_button(interaction, self.bot)
    
    # === Basic Player Commands ===
    
    @commands.hybrid_command(name="play", description="Play audio from a URL or add to queue if already playing")
    async def play(self, ctx: commands.Context, *, url: str):
        """Play audio from URL with support for queuing"""
        try:
            # Delete the user's message if it's a text command
            if not ctx.interaction:
                try:
                    await ctx.message.delete()
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    pass
            
            voice_client = await self.ensure_voice_client(ctx)
            if not voice_client:
                return

            await ctx.defer()
            
            # Check if already playing something
            if voice_client.is_playing() and not voice_client.is_paused():
                # Forward to the queue cog
                queue_cog = self.bot.get_cog('MusicQueue')
                if queue_cog:
                    await queue_cog.add_to_queue(ctx, url=url)
                    return
            
            # Get track info
            track_info = self.player.get_track_info(url)
            
            # Add to queue and get position
            position = self.queue_manager.add_to_queue(ctx.guild.id, track_info)
            
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
                progress_bar = self.ui_helper.create_progress_bar(0, track_info['duration'])
                time_display = f"{self.ui_helper.format_time(0)} / {self.ui_helper.format_time(track_info['duration'])}"
                embed.add_field(
                    name="Duration",
                    value=f"{progress_bar}\n{time_display}",
                    inline=False
                )
                
            # Add queue information
            queue_total = len(self.queue_manager.get_queue(ctx.guild.id))
            embed.add_field(
                name="Queue",
                value=f"Track 1 of {queue_total}",
                inline=True
            )

            # Add format information
            footer_text = ""
            if track_info.get('format') and track_info['format'] != 'Unknown':
                footer_text += f"Format: {track_info['format']}"
            if track_info.get('quality') and track_info['quality'] != 'Unknown':
                if footer_text:
                    footer_text += " | "
                footer_text += f"Quality: {track_info['quality']}"
                
            # Add audio preset info if set
            quality_preset = self.effect_manager.get_quality_preset(ctx.guild.id)
            if quality_preset:
                if footer_text:
                    footer_text += " | "
                footer_text += f"Audio preset: {quality_preset}"
                
            if footer_text:
                embed.set_footer(text=footer_text)
            
            if track_info.get('thumbnail'):
                embed.set_thumbnail(url=track_info['thumbnail'])
            
            # Create view with appropriate controls
            view = MusicControlView(is_live=track_info['is_live'])
            
            self.player.current_track[ctx.guild.id] = track_info
            
            if voice_client.is_playing():
                voice_client.stop()

            if ctx.guild.id in self.player.playing_messages:
                try:
                    await self.player.playing_messages[ctx.guild.id].delete()
                except (discord.errors.NotFound, discord.errors.Forbidden):
                    pass

            message = await ctx.send(embed=embed, view=view)
            self.player.playing_messages[ctx.guild.id] = message
            
            # Get appropriate FFmpeg options
            quality_preset = self.effect_manager.get_quality_preset(ctx.guild.id)
            ffmpeg_options = self.effect_manager.get_ffmpeg_options(
                track_info['is_live'], 
                track_info['platform'],
                quality_preset
            )
            
            # Apply current effect if any
            if ctx.guild.id in self.effect_manager.current_effect:
                effect_name = self.effect_manager.current_effect[ctx.guild.id]
                effect_options = self.effect_manager.get_effect_options(
                    ctx.guild.id, 
                    effect_name,
                    platform=track_info['platform']
                )
                ffmpeg_options.update(effect_options)
            
            await self.player.create_stream_player(
                voice_client, 
                track_info,
                ffmpeg_options
            )
            
            # Only start progress updates for non-live content
            if not track_info['is_live']:
                self.bot.loop.create_task(
                    self.player.start_progress_updates(
                        message, 
                        self.player.current_track[ctx.guild.id],
                        self.ui_helper
                    )
                )

        except Exception as e:
            error_embed = create_embed(
                title="Error Playing Track",
                description=str(e),
                color=discord.Color.red().value
            )
            await ctx.send(embed=error_embed)
    
    @commands.hybrid_command(name="join", description="Join your voice channel")
    async def join(self, ctx: commands.Context):
        """Join the user's voice channel"""
        voice_client = await self.player.join_voice_channel(ctx)
        if voice_client:
            await ctx.send(f"Joined {ctx.author.voice.channel.name}")
    
    @commands.hybrid_command(name="leave", description="Leave the voice channel")
    async def leave(self, ctx: commands.Context):
        """Leave the voice channel"""
        voice_client = self.player.get_voice_client(ctx)
        if voice_client:
            # Clear queue
            self.queue_manager.clear_queue(ctx.guild.id)
            
            # Cancel inactivity timer if running
            self.queue_manager.cancel_inactivity_timer(ctx.guild.id)
            
            # Disconnect
            await voice_client.disconnect()
            self.player.cleanup_for_guild(ctx.guild.id)
            await ctx.send("Left the voice channel")
        else:
            await ctx.send("I'm not in a voice channel")
            
    @commands.hybrid_command(name="pause", description="Pause the current playback")
    async def pause(self, ctx: commands.Context):
        """Pause the current playback"""
        voice_client = self.player.get_voice_client(ctx)
        if not voice_client:
            await ctx.send("I'm not in a voice channel!")
            return
            
        if voice_client.is_playing() and not voice_client.is_paused():
            voice_client.pause()
            await ctx.send("Paused ⏸️")
        else:
            await ctx.send("Nothing is playing!")
            
    @commands.hybrid_command(name="resume", description="Resume paused playback")
    async def resume(self, ctx: commands.Context):
        """Resume paused playback"""
        voice_client = self.player.get_voice_client(ctx)
        if not voice_client:
            await ctx.send("I'm not in a voice channel!")
            return
            
        if voice_client.is_paused():
            voice_client.resume()
            await ctx.send("Resumed ▶️")
        else:
            await ctx.send("Nothing is paused!")
            
    @commands.hybrid_command(name="stop", description="Stop playback and clear queue")
    async def stop(self, ctx: commands.Context):
        """Stop playback and clear queue"""
        voice_client = self.player.get_voice_client(ctx)
        if not voice_client:
            await ctx.send("I'm not in a voice channel!")
            return
            
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
            
        # Clear queue
        self.queue_manager.clear_queue(ctx.guild.id)
        
        # Clear player data
        self.player.cleanup_for_guild(ctx.guild.id)
        
        # Delete now playing message if exists
        if ctx.guild.id in self.player.playing_messages:
            try:
                await self.player.playing_messages[ctx.guild.id].delete()
            except (discord.NotFound, discord.HTTPException):
                pass
                
        await ctx.send("Stopped playback and cleared queue")
        
    @commands.hybrid_command(name="seek", description="Skip to a specific position in seconds")
    async def seek(self, ctx: commands.Context, seconds: int):
        """Skip to a specific position in the track with improved handling"""
        try:
            voice_client = self.player.get_voice_client(ctx)
            if not voice_client:
                await ctx.send("Not connected to a voice channel!")
                return
                
            if not ctx.guild.id in self.player.current_track:
                await ctx.send("Nothing is playing!")
                return
            
            track_data = self.player.current_track[ctx.guild.id]
            if track_data.get('is_live'):
                await ctx.send("Cannot seek in livestreams!")
                return
            
            await ctx.defer()  # Defer the response for longer seeks
                
            current_time = track_data['start_time']
            seek_time = current_time + seconds
            
            # Ensure seek_time is within valid bounds
            seek_time = max(0, min(seek_time, track_data['duration']))
            track_data['start_time'] = seek_time
            
            # Stop current playback
            voice_client.stop()
            
            # Apply current effect with seek
            if ctx.guild.id in self.effect_manager.current_effect:
                effect_name = self.effect_manager.current_effect[ctx.guild.id]
                effect_options = self.effect_manager.get_effect_options(
                    ctx.guild.id, 
                    effect_name, 
                    seek_time,
                    track_data['platform']
                )
                
                audio_source = discord.FFmpegPCMAudio(
                    track_data['url'],
                    **effect_options
                )
            else:
                # Get appropriate FFmpeg options with the current preset
                quality_preset = self.effect_manager.get_quality_preset(ctx.guild.id)
                ffmpeg_options = self.effect_manager.get_ffmpeg_options(
                    track_data['is_live'], 
                    track_data['platform'],
                    quality_preset
                )
                
                # Add seek position
                ffmpeg_options['before_options'] += f' -ss {seek_time}'
                
                audio_source = discord.FFmpegPCMAudio(
                    track_data['url'],
                    **ffmpeg_options
                )
            
            voice_client.play(
                audio_source,
                after=lambda e: print(f'Player error: {e}') if e else None
            )
            
            # Update progress display
            if ctx.guild.id in self.player.playing_messages:
                self.bot.loop.create_task(
                    self.player.start_progress_updates(
                        self.player.playing_messages[ctx.guild.id],
                        track_data,
                        self.ui_helper
                    )
                )
            
            # Send confirmation with embed
            direction = "forward" if seconds > 0 else "backward"
            embed = create_embed(
                title="Position Updated",
                description=(
                    f"Seeked {direction} by {abs(seconds)}s\n"
                    f"Current position: {self.ui_helper.format_time(seek_time)} / "
                    f"{self.ui_helper.format_time(track_data['duration'])}"
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