# cogs/moderation.py
import discord
from discord.ext import commands
from utils.helpers import create_embed
from utils.db_handler import DatabaseHandler
from utils.word_filter import WordFilter
from typing import Optional
from datetime import datetime

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseHandler()
        self.word_filter = WordFilter()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Monitor messages for tracked words"""
        if message.author.bot:
            return

        # Check message for tracked words
        found_words = self.word_filter.check_message(message.content)
        
        if found_words:
            # Update database for each found word
            for word in found_words:
                self.db.log_word_usage(
                    message.author.id,
                    word
                )

    @commands.hybrid_command(name="addword", description="Add a word to track")
    @commands.has_permissions(manage_messages=True)
    async def add_word(self, ctx, *, word: str):
        """Add a new word to track"""
        # Delete the command message to keep the word private
        try:
            await ctx.message.delete()
        except:
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
        
        # Send response as ephemeral message
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="removeword", description="Remove a word from tracking")
    @commands.has_permissions(manage_messages=True)
    async def remove_word(self, ctx, *, word: str):
        """Remove a word from tracking"""
        # Delete the command message to keep the word private
        try:
            await ctx.message.delete()
        except:
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
        
        # Send response as ephemeral message
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="wordstats", description="View word usage statistics")
    @commands.has_permissions(manage_messages=True)
    async def word_stats(self, ctx, user: Optional[discord.Member] = None):
        """View word usage statistics for a user"""
        target_user = user or ctx.author
        stats = self.db.get_user_word_stats(target_user.id)
        
        if not stats:
            await ctx.send(f"No tracked words found for {target_user.name}")
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

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="wordleaderboard", description="View word usage leaderboard")
    @commands.has_permissions(manage_messages=True)
    async def word_leaderboard(self, ctx, word: Optional[str] = None):
        """View leaderboard for word usage"""
        leaderboard = self.db.get_word_leaderboard(word)
        
        if not leaderboard:
            await ctx.send("No word usage data found")
            return

        if word:
            title = f"Leaderboard for specific word"
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

        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))