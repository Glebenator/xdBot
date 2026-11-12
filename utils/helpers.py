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

async def send_hybrid_message(
    ctx,
    *,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    ephemeral: bool = False,
    **kwargs
):
    """Send a private response by interaction or direct message."""
    if not ephemeral:
        return await ctx.send(content=content, embed=embed, **kwargs)
    if ctx.interaction is not None:
        return await ctx.send(content=content, embed=embed, ephemeral=True, **kwargs)
    try:
        return await ctx.author.send(content=content, embed=embed, **kwargs)
    except discord.Forbidden:
        return await ctx.send("Enable direct messages or use the slash command.")


async def defer_hybrid(ctx, *, ephemeral: bool = False) -> bool:
    """Safely defer hybrid command responses when invoked as slash commands.

    Returns True when a defer call was issued, False otherwise. Prefix
    invocations simply return False without raising."""
    interaction = getattr(ctx, "interaction", None)
    if interaction:
        if interaction.response.is_done():
            return False
        await interaction.response.defer(ephemeral=ephemeral)
        return True

    defer = getattr(ctx, "defer", None)
    if callable(defer):
        try:
            await defer()
            return True
        except TypeError:
            return False

    return False
