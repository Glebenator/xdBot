# utils/audio_effects.py
from dataclasses import dataclass
from typing import Dict, Optional
import discord
import asyncio
from utils.audio_constants import (
    FFMPEG_OPTIONS, 
    STREAM_FFMPEG_OPTIONS, 
    PLATFORM_OPTIMIZATIONS,
    AUDIO_QUALITY_PRESETS
)


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
        template='-vn -b:a 256k -af "aresample=resampler=soxr:precision=28:osf=s32:tsf=s32p:dither_method=triangular_hp:filter_size=128" -ac 2 -ar 48000'
    ),
    'bassboost': EffectConfig(
        name='Bass Boost',
        default_intensity=15,
        min_intensity=5,
        max_intensity=50,
        step=5,
        param_name='gain',
        template='-vn -b:a 256k -af "aresample=resampler=soxr:precision=28:osf=s32:tsf=s32p,equalizer=f=40:width_type=h:width=50:g={gain}" -ac 2 -ar 48000'
    ),
    'nightcore': EffectConfig(
        name='Nightcore',
        default_intensity=1.25,
        min_intensity=1.1,
        max_intensity=1.5,
        step=0.05,
        param_name='rate',
        template='-vn -b:a 256k -af "asetrate=44100*{rate},aresample=44100:resampler=soxr,atempo=0.8" -ac 2 -ar 48000'
    ),
    'vaporwave': EffectConfig(
        name='Vaporwave',
        default_intensity=0.8,
        min_intensity=0.5,
        max_intensity=0.9,
        step=0.05,
        param_name='rate',
        template='-vn -b:a 256k -af "asetrate=44100*{rate},aresample=44100:resampler=soxr,atempo=1.25" -ac 2 -ar 48000'
    ),
    'tremolo': EffectConfig(
        name='Tremolo',
        default_intensity=5,
        min_intensity=2,
        max_intensity=10,
        step=1,
        param_name='freq',
        template='-vn -b:a 256k -af "aresample=resampler=soxr,tremolo=f={freq}:d=0.7" -ac 2 -ar 48000'
    ),
    'echo': EffectConfig(
        name='Echo',
        default_intensity=40,
        min_intensity=20,
        max_intensity=100,
        step=10,
        param_name='delay',
        template='-vn -b:a 256k -af "aresample=resampler=soxr,aecho=0.8:0.8:{delay}:0.5" -ac 2 -ar 48000'
    ),
    'radio': EffectConfig(
        name='Radio',
        default_intensity=1.0,
        min_intensity=0.5,
        max_intensity=2.0,
        step=0.1,
        param_name='intensity',
        template='-vn -b:a 256k -af "aresample=resampler=soxr,bandpass=f=1500:width_type=h:width={intensity}*1000,dynaudnorm" -ac 2 -ar 48000'
    ),
    'concert': EffectConfig(
        name='Concert',
        default_intensity=30,
        min_intensity=10, 
        max_intensity=100,
        step=5,
        param_name='reverb',
        template='-vn -b:a 256k -af "aresample=resampler=soxr,stereotools=mlev={reverb}:mode=8:stereo=true" -ac 2 -ar 48000'
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
        # Maps guild_id -> quality_preset (audio quality preset)
        self.quality_presets: Dict[int, str] = {}

    def get_ffmpeg_options(self, is_live: bool, platform: str, quality_preset: Optional[str] = None) -> dict:
        """Get appropriate FFmpeg options based on content type, platform, and quality preset"""
        if is_live:
            base_options = STREAM_FFMPEG_OPTIONS.copy()
            
            # Apply platform-specific optimizations for livestreams
            if platform in PLATFORM_OPTIMIZATIONS:
                platform_opts = PLATFORM_OPTIMIZATIONS[platform]
                if 'audio_options' in platform_opts:
                    # Modify options for this specific platform
                    base_options['options'] = platform_opts['audio_options']
                    
            return base_options
        else:
            base_options = FFMPEG_OPTIONS.copy()
            
            # Apply quality preset if specified
            if quality_preset and quality_preset in AUDIO_QUALITY_PRESETS:
                base_options['options'] = AUDIO_QUALITY_PRESETS[quality_preset]
            # Apply platform-specific optimizations
            elif platform in PLATFORM_OPTIMIZATIONS:
                platform_opts = PLATFORM_OPTIMIZATIONS[platform]
                if 'audio_options' in platform_opts:
                    base_options['options'] = platform_opts['audio_options']
                
            return base_options

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

    def set_quality_preset(self, guild_id: int, preset_name: str) -> bool:
        """Set the audio quality preset for a guild"""
        if preset_name in AUDIO_QUALITY_PRESETS:
            self.quality_presets[guild_id] = preset_name
            return True
        return False

    def get_quality_preset(self, guild_id: int) -> Optional[str]:
        """Get the audio quality preset for a guild"""
        return self.quality_presets.get(guild_id)

    def get_effect_options(self, guild_id: int, effect_name: str, 
                           position: Optional[float] = None,
                           platform: Optional[str] = None) -> dict:
        """Generate FFmpeg options for the current effect with optional platform-specific optimizations"""
        if effect_name == 'none':
            # If platform-specific options are available, use those for 'none' effect
            if platform and platform in PLATFORM_OPTIMIZATIONS:
                options = PLATFORM_OPTIMIZATIONS[platform].get('audio_options', AUDIO_EFFECTS['none'].template)
            else:
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

    def get_available_effects(self) -> Dict[str, str]:
        """Get a dictionary of available effects and their descriptions"""
        return {name: config.name for name, config in AUDIO_EFFECTS.items()}
    
    def get_available_quality_presets(self) -> Dict[str, str]:
        """Get a dictionary of available quality presets"""
        return {
            "standard": "High-quality general purpose audio",
            "voice": "Optimized for speech clarity",
            "music": "Enhanced dynamic range for music",
            "bass_boost": "Enhanced bass response"
        }
            
# Export the class and constants
__all__ = ['AudioEffectManager', 'AUDIO_EFFECTS', 'EffectConfig']