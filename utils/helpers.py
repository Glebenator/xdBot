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