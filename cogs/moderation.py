# cogs/moderation.py
import re
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from utils.db_handler import get_database_handler
from utils.guild_rules import GuildRules, read_rule_defaults
from utils.helpers import create_embed, defer_hybrid, send_hybrid_message

WORD = re.compile(r"[\w]+(?:['-][\w]+)*")


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_database_handler()
        defaults = read_rule_defaults("bad_words.json") or []
        self.rules = GuildRules(self.db, "words", {word.casefold(): True for word in defaults})

    @staticmethod
    def _require_guild(ctx) -> int:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command can only be used in a server context.")
        return ctx.guild.id

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor messages for tracked words"""
        if message.author.bot:
            return

        if message.guild is None:
            return

        words = WORD.findall(message.content.casefold())
        if not words or (await self.bot.get_context(message)).valid:
            return
        tracked = await self.rules.get(message.guild.id)
        matches = [word for word in words if word in tracked]
        if matches:
            await self.db.log_word_usage(
                message.guild.id,
                message.author.id,
                message.author.display_name,
                matches,
                message.id,
                message.channel.id,
            )

    async def _change_word(self, ctx, word: str, add: bool) -> None:
        await defer_hybrid(ctx, ephemeral=True)
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        word = word.strip().casefold()
        if not 1 <= len(word) <= 100 or (add and WORD.fullmatch(word) is None):
            await send_hybrid_message(ctx, content="Enter one word of up to 100 characters.", ephemeral=True)
            return
        changed = await self.rules.set(ctx.guild.id, word, True if add else None)
        if add:
            message = "Word added." if changed else "This word is already tracked."
        else:
            message = "Word removed." if changed else "This word is not tracked."
        await send_hybrid_message(ctx, content=message, ephemeral=True)

    @commands.hybrid_command(name="addword", description="Add a word to track in this server")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def add_word(self, ctx, *, word: str):
        await self._change_word(ctx, word, True)

    @commands.hybrid_command(name="removeword", description="Remove a word from tracking in this server")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def remove_word(self, ctx, *, word: str):
        await self._change_word(ctx, word, False)

    @commands.hybrid_command(name="wordstats", description="View word usage statistics")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def word_stats(self, ctx, user: Optional[discord.Member] = None):
        """View word usage statistics for a user"""
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        await defer_hybrid(ctx, ephemeral=True)
        guild_id = self._require_guild(ctx)
        target_user = user or ctx.author
        stats = await self.db.get_user_word_stats(
            guild_id,
            target_user.id
        )

        if not stats:
            await send_hybrid_message(
                ctx,
                content=f"No tracked words found for {target_user.name}",
                ephemeral=True
            )
            return

        embed = create_embed(
            title=f"Word Statistics for {target_user.name}",
            color=discord.Color.blue().value
        )

        # Add stats for each word
        for stat in stats[:25]:
            last_used = datetime.fromisoformat(stat['last_used'])
            value = f"Count: {stat['usage_count']}\nLast used: {last_used.strftime('%Y-%m-%d %H:%M:%S')}"
            embed.add_field(
                name=f"||{stat['word'][:100]}||",  # Spoiler tags to hide the words
                value=value,
                inline=False
            )

        await send_hybrid_message(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name="wordleaderboard", description="View word usage leaderboard")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def word_leaderboard(self, ctx, word: Optional[str] = None):
        """View leaderboard for word usage"""
        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
        await defer_hybrid(ctx, ephemeral=True)
        guild_id = self._require_guild(ctx)
        leaderboard = await self.db.get_word_leaderboard(
            guild_id,
            word.strip().casefold() if word else None
        )

        if not leaderboard:
            await send_hybrid_message(
                ctx,
                content="No word usage data found",
                ephemeral=True
            )
            return

        if word:
            title = "Leaderboard for specific word"
            description = "Top users for tracked word:"
        else:
            title = "Overall Word Usage Leaderboard"
            description = "Users with most tracked word usage:"

        embed = create_embed(
            title=title,
            description=description,
            color=discord.Color.gold().value
        )

        for i, entry in enumerate(leaderboard, 1):
            if word:
                value = f"Count: {entry['usage_count']}\nLast used: {entry['last_used']}"
            else:
                value = f"Total usage: {entry['total_count']}\nUnique words: {entry['unique_words']}"

            embed.add_field(
                name=f"{i}. {entry['username']}",
                value=value,
                inline=False
            )

        await send_hybrid_message(ctx, embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
