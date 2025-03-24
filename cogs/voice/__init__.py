# cogs/voice/__init__.py
"""
Voice module for Discord bot.
Provides music playback and queue management functionality.
"""
from .player_cog import MusicPlayer
from .queue_cog import MusicQueue
from .effects_cog import AudioEffects

# Setup function to register all voice-related cogs
async def setup(bot):
    await bot.add_cog(MusicPlayer(bot))
    await bot.add_cog(MusicQueue(bot))
    await bot.add_cog(AudioEffects(bot))