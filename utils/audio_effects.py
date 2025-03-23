# utils/audio_effects.py
from dataclasses import dataclass
from typing import Dict, Optional
import discord
import asyncio
from utils.audio_constants import FFMPEG_OPTIONS, STREAM_FFMPEG_OPTIONS


@dataclass
class EffectConfig:
    """Configuration class for audio effects"""
    name: str
    default_intensity: float
    min_intensity: float
    max_intensity: float
    step: float
    param_name: str
    template: str


# Registry of available audio effects
AUDIO_EFFECTS = {
    'none': EffectConfig(
        name='Normal',
        default_intensity=0,
        min_intensity=0,
        max_intensity=0,
        step=0,
        param_name='',
        template='-vn -b:a 192k'
    ),
    'bassboost': EffectConfig(
        name='Bass Boost',
        default_intensity=15,
        min_intensity=5,
        max_intensity=50,
        step=5,
        param_name='gain',
        template='-vn -b:a 192k -af equalizer=f=40:width_type=h:width=50:g={gain}'
    ),
    'nightcore': EffectConfig(
        name='Nightcore',
        default_intensity=1.25,
        min_intensity=1.1,
        max_intensity=1.5,
        step=0.05,
        param_name='rate',
        template='-vn -b:a 192k -af asetrate=44100*{rate},aresample=44100,atempo=0.8'
    ),
    'vaporwave': EffectConfig(
        name='Vaporwave',
        default_intensity=0.8,
        min_intensity=0.5,
        max_intensity=0.9,
        step=0.05,
        param_name='rate',
        template='-vn -b:a 192k -af asetrate=44100*{rate},aresample=44100,atempo=1.25'
    ),
    'tremolo': EffectConfig(
        name='Tremolo',
        default_intensity=5,
        min_intensity=2,
        max_intensity=10,
        step=1,
        param_name='freq',
        template='-vn -b:a 192k -af tremolo=f={freq}:d=0.7'
    ),
    'echo': EffectConfig(
        name='Echo',
        default_intensity=40,
        min_intensity=20,
        max_intensity=100,
        step=10,
        param_name='delay',
        template='-vn -b:a 192k -af aecho=0.8:0.8:{delay}:0.5'
    )
}


class AudioEffectManager:
    def __init__(self):
        # Maps guild_id -> effect_name -> intensity
        self.effect_intensities: Dict[int, Dict[str, float]] = {}
        # Maps guild_id -> effect_name (currently active effect)
        self.current_effect: Dict[int, str] = {}
        # Maps guild_id -> message (effect control message)
        self.effect_messages: Dict[int, discord.Message] = {}

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

    def get_effect_intensity(self, guild_id: int, effect_name: str) -> float:
        """Get the current intensity for an effect"""
        if guild_id not in self.effect_intensities:
            self.effect_intensities[guild_id] = {}
        return self.effect_intensities[guild_id].get(
            effect_name,
            AUDIO_EFFECTS[effect_name].default_intensity
        )

    def set_effect_intensity(self, guild_id: int, effect_name: str, intensity: float) -> None:
        """Set the intensity for an effect"""
        if guild_id not in self.effect_intensities:
            self.effect_intensities[guild_id] = {}
        self.effect_intensities[guild_id][effect_name] = intensity

    def get_effect_options(self, guild_id: int, effect_name: str, 
                           position: Optional[float] = None) -> dict:
        """Generate FFmpeg options for the current effect"""
        if effect_name == 'none':
            options = AUDIO_EFFECTS['none'].template
        else:
            effect_config = AUDIO_EFFECTS[effect_name]
            intensity = self.get_effect_intensity(guild_id, effect_name)
            options = effect_config.template.format(**{effect_config.param_name: intensity})
        
        before_options = FFMPEG_OPTIONS['before_options']
        
        # Add position seek if provided
        if position is not None:
            before_options = f"{before_options} -ss {position}"
            
        return {
            'before_options': before_options,
            'options': options
        }

    async def update_effect_message(self, guild_id: int, effect_name: str, embed_creator) -> None:
        """Update the effect control message with current intensity"""
        if guild_id not in self.effect_messages:
            return

        effect_config = AUDIO_EFFECTS[effect_name]
        current_intensity = self.get_effect_intensity(guild_id, effect_name)
        
        embed = embed_creator(
            title=f"Effect: {effect_config.name}",
            description=(
                f"Current intensity: {current_intensity}\n"
                f"Min: {effect_config.min_intensity} | "
                f"Max: {effect_config.max_intensity} | "
                f"Step: {effect_config.step}"
            ),
            color=discord.Color.blue().value
        )
        
        try:
            await self.effect_messages[guild_id].edit(embed=embed)
        except discord.NotFound:
            self.effect_messages.pop(guild_id, None)
            
# Export the class and constants
__all__ = ['AudioEffectManager', 'AUDIO_EFFECTS', 'EffectConfig', 'FFMPEG_OPTIONS', 'STREAM_FFMPEG_OPTIONS']