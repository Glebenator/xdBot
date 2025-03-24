# cogs/voice/__init__.py
"""Voice module for Discord music bot functionality."""

from .voice_cog import Voice

async def setup(bot):
    """
    Set up the voice cog.
    
    Args:
        bot: Discord bot instance
    """
    await bot.add_cog(Voice(bot))