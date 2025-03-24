# cogs/voice/effects_cog.py
"""
Audio effects for music bot.
Provides commands to apply various audio effects to playback.
"""
import discord
from discord.ext import commands
import logging
from typing import Optional

from .base_cog import BaseVoiceCog
from utils.helpers import create_embed
from utils.player_ui import EffectControlView
from utils.audio_effects import AUDIO_EFFECTS


class AudioEffects(BaseVoiceCog):
    """Audio effects for music playback"""
    
    def __init__(self, bot):
        super().__init__(bot)
        
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

        # Get effect options with platform consideration
        effect_options = self.effect_manager.get_effect_options(
            ctx.guild.id, 
            effect_name, 
            current_position,
            track_data['platform']
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

    @commands.hybrid_command(name="effects", description="List all available audio effects")
    async def list_effects(self, ctx: commands.Context):
        """List all available audio effects"""
        effects = self.effect_manager.get_available_effects()
        
        embed = create_embed(
            title="Available Audio Effects",
            description="Here are all the available audio effects:",
            color=discord.Color.blue().value
        )
        
        for name, description in effects.items():
            embed.add_field(
                name=name,
                value=description,
                inline=True
            )
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="audiopreset", description="Set the audio quality preset for playback")
    async def set_audio_preset(self, ctx: commands.Context, preset_name: str):
        """Set the audio quality preset for playback"""
        presets = self.effect_manager.get_available_quality_presets()
        
        if preset_name not in presets:
            preset_list = ', '.join(f'`{preset}`' for preset in presets.keys())
            await ctx.send(f"Invalid preset! Available presets: {preset_list}")
            return
            
        self.effect_manager.set_quality_preset(ctx.guild.id, preset_name)
        
        # If currently playing, apply the preset
        voice_client = self.player.get_voice_client(ctx)
        if voice_client and voice_client.is_playing() and ctx.guild.id in self.player.current_track:
            track_data = self.player.current_track[ctx.guild.id]
            voice_client.stop()
            
            # Get appropriate FFmpeg options with the new preset
            ffmpeg_options = self.effect_manager.get_ffmpeg_options(
                track_data['is_live'], 
                track_data['platform'],
                preset_name
            )
            
            # Apply current effect if any
            if ctx.guild.id in self.effect_manager.current_effect:
                effect_name = self.effect_manager.current_effect[ctx.guild.id]
                effect_options = self.effect_manager.get_effect_options(
                    ctx.guild.id, 
                    effect_name,
                    track_data['start_time'],
                    track_data['platform']
                )
                ffmpeg_options.update(effect_options)
            
            await self.player.create_stream_player(
                voice_client, 
                track_data,
                ffmpeg_options
            )
            
            await ctx.send(f"Applied audio preset: `{preset_name}` to current playback")
        else:
            await ctx.send(f"Set audio preset to: `{preset_name}`. Will apply to next playback.")

    @commands.hybrid_command(name="audiopresets", description="List all available audio quality presets")
    async def list_audio_presets(self, ctx: commands.Context):
        """List all available audio quality presets"""
        presets = self.effect_manager.get_available_quality_presets()
        
        embed = create_embed(
            title="Available Audio Quality Presets",
            description="Here are all the available audio quality presets:",
            color=discord.Color.blue().value
        )
        
        for name, description in presets.items():
            embed.add_field(
                name=name,
                value=description,
                inline=False
            )
            
        # Show current preset if set
        current_preset = self.effect_manager.get_quality_preset(ctx.guild.id)
        if current_preset:
            embed.set_footer(text=f"Current preset: {current_preset}")
            
        await ctx.send(embed=embed)