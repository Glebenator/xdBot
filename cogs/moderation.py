# cogs/moderation.py
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from utils.db_handler import get_database_handler
from utils.helpers import create_embed, defer_hybrid, send_hybrid_message
from utils.word_filter import WordFilter


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_database_handler()
        self.word_filter = WordFilter()

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

        # Check message for tracked words
        found_words = self.word_filter.check_message(message.content)

        if found_words:
            # Update database for each found word
            for word in found_words:
                await self.db.log_word_usage(
                    message.guild.id,
                    message.author.id,
                    word,
                    message_id=message.id,
                    channel_id=message.channel.id
                )

    @commands.hybrid_command(name="addword", description="Add a word to track")
    @commands.has_permissions(manage_messages=True)
    async def add_word(self, ctx, *, word: str):
        """Add a new word to track"""
        await defer_hybrid(ctx, ephemeral=True)
        # Delete the command message to keep the word private
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if self.word_filter.add_word(word):
            embed = create_embed(
                title="Word Added",
                description="The specified word has been added to the tracking list.",
                color=discord.Color.green().value
            )
        else:
            embed = create_embed(
                title="Already Tracked",
                description="This word is already being tracked.",
                color=discord.Color.yellow().value
            )

        # Send response appropriately for the context
        await send_hybrid_message(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name="removeword", description="Remove a word from tracking")
    @commands.has_permissions(manage_messages=True)
    async def remove_word(self, ctx, *, word: str):
        """Remove a word from tracking"""
        await defer_hybrid(ctx, ephemeral=True)
        # Delete the command message to keep the word private
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if self.word_filter.remove_word(word):
            embed = create_embed(
                title="Word Removed",
                description="The specified word has been removed from tracking.",
                color=discord.Color.green().value
            )
        else:
            embed = create_embed(
                title="Not Found",
                description="This word was not being tracked.",
                color=discord.Color.yellow().value
            )

        # Send response appropriately for the context
        await send_hybrid_message(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name="wordstats", description="View word usage statistics")
    @commands.has_permissions(manage_messages=True)
    async def word_stats(self, ctx, user: Optional[discord.Member] = None):
        """View word usage statistics for a user"""
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
        for stat in stats:
            last_used = datetime.fromisoformat(stat['last_used'])
            value = f"Count: {stat['usage_count']}\nLast used: {last_used.strftime('%Y-%m-%d %H:%M:%S')}"
            embed.add_field(
                name=f"||{stat['word']}||",  # Spoiler tags to hide the words
                value=value,
                inline=False
            )

        await send_hybrid_message(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(name="wordleaderboard", description="View word usage leaderboard")
    @commands.has_permissions(manage_messages=True)
    async def word_leaderboard(self, ctx, word: Optional[str] = None):
        """View leaderboard for word usage"""
        await defer_hybrid(ctx, ephemeral=True)
        guild_id = self._require_guild(ctx)
        leaderboard = await self.db.get_word_leaderboard(
            guild_id,
            word
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
