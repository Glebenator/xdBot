# cogs/voice.py
import discord
from discord.ext import commands
import os
import asyncio
import logging
from typing import Optional

from utils.helpers import create_embed
from utils.audio_constants import FFMPEG_OPTIONS, STREAM_FFMPEG_OPTIONS
from utils.player_ui import MusicControlView, EffectControlView, PlayerUIHelper
from utils.audio_effects import AudioEffectManager, AUDIO_EFFECTS
from utils.music_player import MusicPlayer


class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        try:
            # Initialize helpers
            self.player = MusicPlayer()
            self.effect_manager = AudioEffectManager()
            self.ui_helper = PlayerUIHelper()
        except Exception as e:
            print(f"Error initializing Voice cog: {e}")
            raise
    
    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        # Disconnect all voice clients
        for voice_client in self.player.voice_clients.values():
            try:
                await voice_client.disconnect()
            except:
                pass
    
    # === Helper Methods ===
    
    def get_track_data(self, guild_id: int):
        """Get current track data for a guild"""
        return self.player.current_track.get(guild_id)
    
    def cleanup_for_guild(self, guild_id: int):
        """Clean up resources for a guild"""
        # Remove voice client
        if guild_id in self.player.voice_clients:
            self.player.voice_clients.pop(guild_id, None)
        
        # Remove track data
        if guild_id in self.player.current_track:
            self.player.current_track.pop(guild_id, None)
        
        # Remove playing message
        if guild_id in self.player.playing_messages:
            self.player.playing_messages.pop(guild_id, None)
    
    # === Button Handling ===
    
    async def handle_effect_button(self, interaction: discord.Interaction) -> None:
        """Handle effect control button interactions"""
        custom_id = interaction.data["custom_id"]
        guild_id = interaction.guild_id
        
        if guild_id not in self.effect_manager.current_effect:
            await self.ui_helper.send_temporary_response(interaction, "No effect currently active!", ephemeral=True)
            return

        effect_name = self.effect_manager.current_effect[guild_id]
        effect_config = AUDIO_EFFECTS[effect_name]
        current_intensity = self.effect_manager.get_effect_intensity(guild_id, effect_name)

        if custom_id.startswith("decrease"):
            new_intensity = max(
                effect_config.min_intensity,
                current_intensity - effect_config.step
            )
        elif custom_id.startswith("increase"):
            new_intensity = min(
                effect_config.max_intensity,
                current_intensity + effect_config.step
            )
        elif custom_id.startswith("reset"):
            new_intensity = effect_config.default_intensity
        else:
            await self.ui_helper.send_temporary_response(interaction, "Invalid button!", ephemeral=True)
            return

        # Update intensity and reapply effect
        self.effect_manager.set_effect_intensity(guild_id, effect_name, new_intensity)
        await self.effect_manager.update_effect_message(guild_id, effect_name, create_embed)
        
        # Get the context from the interaction
        ctx = await self.bot.get_context(interaction.message)
        await self.apply_effect(ctx, effect_name)
        
        # Acknowledge the button press
        await self.ui_helper.send_temporary_response(
            interaction,
            f"Effect intensity updated to {new_intensity}", 
            ephemeral=True
        )
    
    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks"""
        voice_client = self.player.get_voice_client(interaction)
        if not voice_client:
            await self.ui_helper.send_temporary_response(interaction, "Not connected to a voice channel!")
            return

        custom_id = interaction.data["custom_id"]
        track_data = self.get_track_data(interaction.guild_id)

        if custom_id.startswith(("increase_", "decrease_", "reset_")):
            await self.handle_effect_button(interaction)
            return
    
        if not track_data:
            await self.ui_helper.send_temporary_response(interaction, "No track data available!")
            return
        
        try:
            if track_data.get('is_live'):
                # Handle livestream controls
                if custom_id == "pause":
                    success = await self.player.handle_stream_command(voice_client, track_data, "pause")
                    if success:
                        await self.ui_helper.send_temporary_response(interaction, "Stream paused ⏸️")
                    else:
                        await self.ui_helper.send_temporary_response(interaction, "Failed to pause stream")
                        
                elif custom_id == "resume":
                    success = await self.player.handle_stream_command(voice_client, track_data, "resume")
                    if success:
                        await self.ui_helper.send_temporary_response(interaction, "Stream resumed ▶️")
                    else:
                        await self.ui_helper.send_temporary_response(interaction, "Failed to resume stream")
                        
                elif custom_id == "stop":
                    success = await self.player.handle_stream_command(voice_client, track_data, "stop")
                    if success:
                        # Clean up
                        self.cleanup_for_guild(interaction.guild_id)
                        await voice_client.disconnect()
                        
                        # Delete the now playing message
                        if interaction.guild_id in self.player.playing_messages:
                            try:
                                await self.player.playing_messages[interaction.guild_id].delete()
                            except (discord.NotFound, discord.HTTPException):
                                pass
                        
                        await self.ui_helper.send_temporary_response(interaction, "Stream stopped and disconnected ⏹️")
                    else:
                        await self.ui_helper.send_temporary_response(interaction, "Failed to stop stream")
            else:
                if custom_id == "pause":
                    if voice_client.is_playing() and not voice_client.is_paused():
                        voice_client.pause()
                        await self.ui_helper.send_temporary_response(interaction, "Paused ⏸️")
                    else:
                        await self.ui_helper.send_temporary_response(interaction, "Nothing is playing!")
                        
                elif custom_id == "resume":
                    if voice_client.is_paused():
                        voice_client.resume()
                        await self.ui_helper.send_temporary_response(interaction, "Resumed ▶️")
                    else:
                        await self.ui_helper.send_temporary_response(interaction, "Not paused!")
                        
                elif custom_id == "stop":
                    if voice_client.is_playing() or voice_client.is_paused():
                        voice_client.stop()
                    
                    # Clean up
                    self.cleanup_for_guild(interaction.guild_id)
                    
                    # Disconnect from voice
                    await voice_client.disconnect()
                    
                    # Delete the now playing message
                    if interaction.guild_id in self.player.playing_messages:
                        try:
                            await self.player.playing_messages[interaction.guild_id].delete()
                        except (discord.NotFound, discord.HTTPException):
                            pass
                    
                    await self.ui_helper.send_temporary_response(interaction, "Stopped and left the channel ⏹️")
                        
                elif custom_id in ["forward", "rewind"]:
                    if not interaction.guild_id in self.player.current_track:
                        await self.ui_helper.send_temporary_response(interaction, "Nothing is playing!")
                        return
                        
                    track_data = self.player.current_track[interaction.guild_id]
                    current_time = track_data['start_time']
                    seek_time = current_time + 10 if custom_id == "forward" else current_time - 10
                    
                    seek_time = max(0, min(seek_time, track_data['duration']))
                    track_data['start_time'] = seek_time
                    
                    voice_client.stop()
                    
                    await self.player.create_stream_player(
                        voice_client, 
                        track_data,
                        {'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seek_time}',
                         'options': '-vn -b:a 192k'}
                    )
                    
                    direction = "Forward" if custom_id == "forward" else "Backward"
                    await self.ui_helper.send_temporary_response(
                        interaction,
                        f"{direction} 10s ({'%.1f' % seek_time}s / {track_data['duration']}s)"
                    )
        except Exception as e:
            await self.ui_helper.send_temporary_response(
                interaction,
                f"Error handling button click: {str(e)}",
                delete_after=10.0
            )
    
    # === Commands ===
    
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
            await voice_client.disconnect()
            self.cleanup_for_guild(ctx.guild.id)
            await ctx.send("Left the voice channel")
        else:
            await ctx.send("I'm not in a voice channel")
    
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
            
            voice_client = await self.player.join_voice_channel(ctx)
            if not voice_client:
                return

            async with ctx.typing():
                track_info = self.player.get_track_info(url)
                
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

                if track_info.get('format'):
                    embed.set_footer(text=f"Format: {track_info['format']} | Quality: {track_info['quality']}")
                
                if track_info.get('thumbnail'):
                    embed.set_thumbnail(url=track_info['thumbnail'])
                
                # Create view with appropriate controls
                view = MusicControlView(is_live=track_info['is_live'])
                
                self.player.current_track[ctx.guild.id] = {
                    'title': track_info['title'],
                    'url': track_info['url'],
                    'duration': track_info['duration'],
                    'start_time': 0,
                    'is_live': track_info['is_live'],
                    'platform': track_info['platform']
                }
                
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
                ffmpeg_options = self.effect_manager.get_ffmpeg_options(
                    track_info['is_live'], 
                    track_info['platform']
                )
                
                # Apply current effect if any
                if ctx.guild.id in self.effect_manager.current_effect:
                    effect_name = self.effect_manager.current_effect[ctx.guild.id]
                    effect_options = self.effect_manager.get_effect_options(ctx.guild.id, effect_name)
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
    
    @commands.command(name="effect", description="Apply an audio effect to the currently playing track")
    async def apply_effect(self, ctx: commands.Context, effect_name: str) -> None:
        """Apply an audio effect to the currently playing track"""
        if effect_name not in AUDIO_EFFECTS:
            effects_list = ', '.join(f'`{effect}`' for effect in AUDIO_EFFECTS.keys())
            await ctx.send(f"Invalid effect! Available effects: {effects_list}")
            return

        if not ctx.guild.id in self.player.current_track:
            await ctx.send("Nothing is playing!")
            return

        voice_client = self.player.get_voice_client(ctx)
        if not voice_client:
            await ctx.send("Not connected to a voice channel!")
            return

        # Set the current effect for the guild
        self.effect_manager.current_effect[ctx.guild.id] = effect_name

        # Get track data
        track_data = self.player.current_track[ctx.guild.id]
        current_position = track_data['start_time']

        # Get effect options
        effect_options = self.effect_manager.get_effect_options(
            ctx.guild.id, 
            effect_name, 
            current_position
        )

        # Apply the effect
        voice_client.stop()
        audio_source = discord.FFmpegPCMAudio(
            track_data['url'],
            **effect_options
        )

        voice_client.play(
            audio_source,
            after=lambda e: print(f'Player error: {e}') if e else None
        )

        # Send or update control message
        effect_config = AUDIO_EFFECTS[effect_name]
        embed = create_embed(
            title=f"Effect: {effect_config.name}",
            description=(
                "No adjustments available" if effect_name == 'none' else
                f"Current intensity: {self.effect_manager.get_effect_intensity(ctx.guild.id, effect_name)}\n"
                f"Min: {effect_config.min_intensity} | "
                f"Max: {effect_config.max_intensity} | "
                f"Step: {effect_config.step}"
            ),
            color=discord.Color.blue().value
        )

        # Delete old effect message if it exists
        if ctx.guild.id in self.effect_manager.effect_messages:
            try:
                await self.effect_manager.effect_messages[ctx.guild.id].delete()
            except discord.NotFound:
                pass

        # Send new effect message with controls
        message = await ctx.send(
            embed=embed,
            view=EffectControlView(effect_name)
        )
        self.effect_manager.effect_messages[ctx.guild.id] = message
    
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
                    seek_time
                )
                
                audio_source = discord.FFmpegPCMAudio(
                    track_data['url'],
                    **effect_options
                )
            else:
                # Default options with seek
                seek_options = {
                    'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seek_time}',
                    'options': '-vn -b:a 192k'
                }
                
                audio_source = discord.FFmpegPCMAudio(
                    track_data['url'],
                    **seek_options
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


async def setup(bot):
    cog = Voice(bot)
    bot.add_listener(cog.on_button_click, "on_interaction")
    await bot.add_cog(cog)