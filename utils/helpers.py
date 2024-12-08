# utils/helpers.py
from typing import Optional
import discord

def create_embed(
    title: str,
    description: Optional[str] = None,
    color: int = discord.Color.red().value
) -> discord.Embed:
    """Create a standardized embed for the bot"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    return embed