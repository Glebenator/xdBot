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
    """Send a message that supports both prefix and slash contexts.

    When ephemeral is requested, the message will be ephemeral only if the
    current context originated from an interaction; otherwise it falls back
    to a regular channel message.
    """
    kwargs = dict(kwargs)
    kwargs.pop("ephemeral", None)

    interaction = getattr(ctx, "interaction", None)

    if ephemeral and interaction:
        if interaction.response.is_done():
            return await interaction.followup.send(
                content=content,
                embed=embed,
                ephemeral=True,
                **kwargs
            )
        await interaction.response.send_message(
            content=content,
            embed=embed,
            ephemeral=True,
            **kwargs
        )
        return None

    return await ctx.send(
        content=content,
        embed=embed,
        **kwargs
    )


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