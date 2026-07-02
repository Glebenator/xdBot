from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import discord
from discord.ext import commands

from utils.db_handler import get_database_handler
from utils.helpers import create_embed, defer_hybrid

MAX_QUOTE_LENGTH = 1000


class Quotes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_database_handler()

    @staticmethod
    def _require_guild(ctx) -> Optional[int]:
        if ctx.guild is None:
            return None
        return ctx.guild.id

    @staticmethod
    def _display_name(user: Any) -> str:
        return getattr(user, "display_name", None) or getattr(user, "name", "Unknown")

    @staticmethod
    def _clean_quote_text(text: str) -> str:
        quote = text.strip()
        if len(quote) > MAX_QUOTE_LENGTH:
            raise ValueError(f"Quotes must be {MAX_QUOTE_LENGTH} characters or less.")
        if not quote:
            raise ValueError("Quotes cannot be empty.")
        return quote

    @staticmethod
    def _shorten(text: str, limit: int = 220) -> str:
        text = text.strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _format_date(value: Optional[str]) -> str:
        if not value:
            return "Unknown date"
        try:
            return datetime.fromisoformat(value).strftime("%Y-%m-%d")
        except ValueError:
            return value

    def _build_quote_embed(self, quote: dict[str, Any], *, title: str = "Quote Hall") -> discord.Embed:
        quoted_username = quote.get("quoted_username") or "Unknown"
        quote_text = quote.get("quote_text", "")
        saved_by = quote.get("saved_by_username") or "Unknown"
        created_at = self._format_date(quote.get("created_at"))

        embed = create_embed(
            title=title,
            description=f"> {quote_text}",
            color=discord.Color.gold().value,
        )
        embed.add_field(name="Quoted", value=quoted_username, inline=True)
        embed.add_field(name="Saved By", value=saved_by, inline=True)
        embed.add_field(name="Date", value=created_at, inline=True)

        footer_parts = [f"Quote #{quote.get('id')}"]
        channel_id = quote.get("channel_id")
        message_id = quote.get("message_id")
        if channel_id and message_id:
            footer_parts.append(f"source: {message_id}")
        embed.set_footer(text=" | ".join(footer_parts))
        return embed

    async def _fetch_source_message(
        self,
        ctx,
        source: Optional[str],
    ) -> Optional[discord.Message]:
        if source and source.isdigit():
            try:
                return await ctx.channel.fetch_message(int(source))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                raise ValueError("I could not find that message in this channel.")

        message = getattr(ctx, "message", None)
        reference = getattr(message, "reference", None)
        if reference and reference.message_id:
            resolved = getattr(reference, "resolved", None)
            if isinstance(resolved, discord.Message):
                return resolved

            try:
                return await ctx.channel.fetch_message(reference.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                raise ValueError("I could not load the message you replied to.")

        return None

    async def _send_random_quote(self, ctx, user: Optional[discord.Member] = None) -> None:
        await defer_hybrid(ctx)
        guild_id = self._require_guild(ctx)
        if guild_id is None:
            await ctx.send("Quote Hall only works in a server.")
            return

        quote = await self.db.get_random_quote(
            guild_id,
            quoted_user_id=user.id if user else None,
        )
        if not quote:
            if user:
                await ctx.send(f"No quotes saved for {user.display_name} yet.")
            else:
                await ctx.send("No quotes saved yet. Reply to a message with `quote add` to start one.")
            return

        await ctx.send(embed=self._build_quote_embed(quote, title="Random Quote"))

    @commands.hybrid_group(
        name="quote",
        invoke_without_command=True,
        description="Show a random saved quote",
    )
    async def quote(self, ctx):
        await self._send_random_quote(ctx)

    @quote.command(name="add", description="Save a message or text to Quote Hall")
    async def quote_add(
        self,
        ctx,
        source: Optional[str] = None,
        *,
        text: Optional[str] = None,
    ):
        """Save a quote.

        Reply to a message and run this command, pass a message ID from the
        current channel, or provide text manually.
        """
        await defer_hybrid(ctx)
        guild_id = self._require_guild(ctx)
        if guild_id is None:
            await ctx.send("Quote Hall only works in a server.")
            return

        try:
            source_message = await self._fetch_source_message(ctx, source)
            if source_message:
                quote_text = self._clean_quote_text(
                    source_message.clean_content or source_message.content
                )
                quoted_user_id = source_message.author.id
                quoted_username = self._display_name(source_message.author)
                channel_id = source_message.channel.id
                message_id = source_message.id
            else:
                manual_text = " ".join(part for part in (source, text) if part).strip()
                quote_text = self._clean_quote_text(manual_text)
                quoted_user_id = ctx.author.id
                quoted_username = self._display_name(ctx.author)
                channel_id = None
                message_id = None

            quote = await self.db.add_quote(
                guild_id,
                quote_text,
                quoted_user_id=quoted_user_id,
                quoted_username=quoted_username,
                saved_by_user_id=ctx.author.id,
                saved_by_username=self._display_name(ctx.author),
                channel_id=channel_id,
                message_id=message_id,
            )
        except ValueError as exc:
            await ctx.send(f"Could not save quote: {exc}")
            return

        title = "Already In Quote Hall" if quote.get("duplicate") else "Saved To Quote Hall"
        await ctx.send(embed=self._build_quote_embed(quote, title=title))

    @quote.command(name="random", description="Show a random saved quote")
    async def quote_random(self, ctx):
        await self._send_random_quote(ctx)

    @quote.command(name="user", description="Show a random quote from a user")
    async def quote_user(self, ctx, user: discord.Member):
        await self._send_random_quote(ctx, user)

    @quote.command(name="list", description="Show recent saved quotes")
    async def quote_list(
        self,
        ctx,
        user: Optional[discord.Member] = None,
        limit: int = 5,
    ):
        await defer_hybrid(ctx)
        guild_id = self._require_guild(ctx)
        if guild_id is None:
            await ctx.send("Quote Hall only works in a server.")
            return

        limit = max(1, min(limit, 10))
        quotes = await self.db.list_quotes(
            guild_id,
            quoted_user_id=user.id if user else None,
            limit=limit,
        )
        if not quotes:
            if user:
                await ctx.send(f"No quotes saved for {user.display_name} yet.")
            else:
                await ctx.send("No quotes saved yet.")
            return

        title = f"Recent Quotes For {user.display_name}" if user else "Recent Quotes"
        embed = create_embed(title=title, color=discord.Color.gold().value)
        for quote in quotes:
            quoted_username = quote.get("quoted_username") or "Unknown"
            value = self._shorten(quote.get("quote_text", ""))
            embed.add_field(
                name=f"#{quote.get('id')} - {quoted_username}",
                value=f"> {value}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @quote.command(name="delete", description="Delete a saved quote")
    async def quote_delete(self, ctx, quote_id: int):
        await defer_hybrid(ctx, ephemeral=True)
        guild_id = self._require_guild(ctx)
        if guild_id is None:
            await ctx.send("Quote Hall only works in a server.")
            return

        quote = await self.db.get_quote(guild_id, quote_id)
        if not quote:
            await ctx.send(f"Quote #{quote_id} was not found.")
            return

        permissions = getattr(ctx.author, "guild_permissions", None)
        can_manage = bool(
            permissions and (permissions.manage_messages or permissions.administrator)
        )
        can_delete = (
            can_manage
            or quote.get("saved_by_user_id") == ctx.author.id
            or quote.get("quoted_user_id") == ctx.author.id
        )
        if not can_delete:
            await ctx.send("You can only delete quotes you saved or quotes attributed to you.")
            return

        deleted = await self.db.delete_quote(guild_id, quote_id)
        if deleted:
            await ctx.send(f"Deleted quote #{quote_id}.")
        else:
            await ctx.send(f"Quote #{quote_id} was already deleted.")


async def setup(bot):
    await bot.add_cog(Quotes(bot))
