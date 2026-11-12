# cogs/fun.py
import logging
import random
from datetime import datetime, timedelta

import discord
from discord.ext import commands

import config
from utils.db_handler import get_database_handler
from utils.helpers import create_embed, defer_hybrid
from utils.rng import RandomOrgRNG


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_database_handler()
        self.random_org_enabled = config.settings.random_org_enabled
        if not self.random_org_enabled:
            logging.warning(
                "RANDOM_ORG_KEY is not set. Games use the local random number generator."
            )
        self.rng = RandomOrgRNG(config.settings.random_org_api_key)

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        await self.rng.close()

    @staticmethod
    def _require_guild(ctx) -> int:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command can only be used in a server context.")
        return ctx.guild.id

    @staticmethod
    def process_success_roll(number: int) -> tuple[str, int]:
        """Process a success roll and return the message and success level"""
        if number < 5:
            return "📉 Massive anti-success " + str(number), 1
        elif number < 10:
            return "🗑️ garbage success " + str(number), 2
        elif number < 50:
            return "❌ is not successful today " + str(number), 3
        elif number < 75:
            return "📈 is somewhat successful today " + str(number), 4
        elif number < 90:
            return "💰 is very successful today " + str(number), 5
        else:
            return "🌟 IS A MASSIVE SUCCESSFUL BUSINESSMAN " + str(number), 6

    async def _send_cooldown(self, ctx, next_roll: datetime) -> None:
        minutes = max(0, int((next_roll - datetime.now()).total_seconds() / 60))
        hours, minutes = divmod(minutes, 60)
        await ctx.send(embed=create_embed(
            title="Command on Cooldown",
            description=f"You can roll again in {hours} hours and {minutes} minutes.",
            color=discord.Color.red().value,
        ))

    @commands.hybrid_command(name="успех", description="Roll for success once every 12 hours")
    @commands.guild_only()
    async def success(self, ctx):
        """Roll for success and update the server leaderboard."""
        await defer_hybrid(ctx)
        guild_id = self._require_guild(ctx)
        user = ctx.author
        last_used = await self.db.get_command_cooldown(guild_id, user.id, "успех")
        if last_used:
            next_roll = last_used + timedelta(hours=12)
            if datetime.now() < next_roll:
                await self._send_cooldown(ctx, next_roll)
                return

        number = await self.rng.randint(1, 100)
        message, points = self.process_success_roll(number)
        next_roll, streak, elapsed_days = await self.db.record_success_roll(
            guild_id, user.id, user.name, number, points
        )
        if next_roll is not None:
            await self._send_cooldown(ctx, next_roll)
            return

        if elapsed_days == 1:
            message += f"\nStreak continued. Current streak is {streak} days."
        elif elapsed_days not in (None, 0):
            message += "\nYour streak started again."
        if not self.random_org_enabled:
            message += "\nThis roll used the local random number generator."
        await ctx.send(f"{user.mention} {message}")

    @commands.hybrid_command(
    name="топ",
    description="View the success leaderboard"
)
    async def success_leaderboard(self, ctx):
        """View the успех command leaderboard"""
        await defer_hybrid(ctx)
        guild_id = self._require_guild(ctx)
        leaderboard_data = await self.db.get_success_leaderboard(guild_id)

        if not leaderboard_data:
            await ctx.send("No успех data available yet!")
            return

        embed = create_embed(
            title="🏆 Business Empire Leaderboard 🏆",
            description="The most successful businessmen:",
            color=discord.Color.gold().value
        )

        # Safely get the maximum success score
        max_success = 0
        for entry in leaderboard_data:
            success = entry.get('total_success', 0)  # Use get() with default value
            if success > max_success:
                max_success = success

        # Format leaderboard entries
        for i, entry in enumerate(leaderboard_data, 1):
            # Safely get all values with defaults
            total_success = entry.get('total_success', 0)
            success_streak = entry.get('success_streak', 0)
            highest_success = entry.get('highest_success', 0)
            avg_success = entry.get('avg_success', 0)
            total_attempts = entry.get('total_attempts', 0)
            username = entry.get('username', 'Unknown User')

            # Determine medal and rank formatting
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👔"

            # Calculate success bar (protect against division by zero)
            progress = min(1.0, total_success / max_success) if max_success > 0 else 0
            bar_length = 8
            filled = int(bar_length * progress)
            bar = "▰" * filled + "▱" * (bar_length - filled)

            # Format achievements
            achievements = []
            if success_streak >= 7:
                achievements.append(f"🔥 {success_streak}d Streak")
            if highest_success == 6:
                achievements.append("⭐ Perfect Roll")

            # Calculate success tier
            if total_success >= 1000:
                tier = "💎 Business Legend"
            elif total_success >= 500:
                tier = "👑 Business Mogul"
            elif total_success >= 250:
                tier = "💼 Business Expert"
            elif total_success >= 100:
                tier = "📈 Rising Star"
            else:
                tier = "👔 Beginner"

            # Format the entry text
            value = [
                f"{bar} **{total_success}** pts",
                f"Rank: {tier}",
                f"Avg Success: {avg_success:.1f} ({total_attempts} attempts)"
            ]

            if achievements:
                value.append(f"Achievements: {' '.join(achievements)}")

            embed.add_field(
                name=f"{medal} #{i} {username}",
                value="\n".join(value),
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="успехстат",
        description="View your success statistics and achievements"
    )
    async def success_stats(self, ctx):
        """View detailed success statistics"""
        await defer_hybrid(ctx)
        guild_id = self._require_guild(ctx)
        stats = await self.db.get_success_stats(guild_id, ctx.author.id)

        embed = create_embed(
            title=f"Success Stats for {ctx.author.name}",
            color=discord.Color.gold().value
        )

        # Calculate success rank based on total success
        total_success = stats['total_success']
        if total_success >= 1000:
            rank = "💎 Business Legend"
        elif total_success >= 500:
            rank = "👑 Business Mogul"
        elif total_success >= 250:
            rank = "💼 Business Expert"
        elif total_success >= 100:
            rank = "📈 Rising Star"
        else:
            rank = "👔 Beginner"

        # Main stats
        embed.add_field(
            name="Business Rank",
            value=f"{rank}\n{total_success} total points",
            inline=False
        )

        # Streak and Abilities
        streak_text = f"🔥 {stats['success_streak']} days"

        embed.add_field(
            name="Current Streak",
            value=streak_text,
            inline=True
        )

        # Last check timestamp
        if stats['last_success_check']:
            last_check = datetime.fromisoformat(stats['last_success_check'])
            embed.add_field(
                name="Last Check",
                value=f"📅 {last_check.strftime('%Y-%m-%d %H:%M')}",
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="огурчик", description="Насколько ты откушал огурчик")
    async def cucumber(self, ctx):
        """Check how much cucumber you have eaten"""
        number = random.randint(0, 100)
        mention = ctx.author.mention
        if number == 0:
            await ctx.send(f"{mention} нихуя не откушал")
        elif number == 100:
            await ctx.send(f"{mention} сьел весь огурчик 🥒")
        else:
            await ctx.send(f"{mention} откушал {number}% огурчика 🥒")

    @commands.hybrid_command(name="roll", description="Roll a random number using Random.org")
    @commands.guild_only()
    async def roll(self, ctx, max_num: commands.Range[int, 1, 1_000_000_000] = 100):
        """Roll a random number between 1 and max_num using true randomness from Random.org"""
        await defer_hybrid(ctx)  # Acknowledge command while we wait for Random.org

        # Update database
        guild_id = self._require_guild(ctx)

        await self.db.update_user(
            guild_id,
            ctx.author.id,
            ctx.author.name
        )

        try:
            number = await self.rng.randint(1, max_num)
            await self.db.log_command_usage(
                guild_id,
                ctx.author.id,
                "roll",
                roll_value=number
            )
            response = f"{ctx.author.mention} rolled {number} 🎲"
            if not self.random_org_enabled:
                response += "\nℹ️ True randomness unavailable; using fallback RNG until a Random.org key is configured."
            await ctx.send(response)
        except Exception:
            await ctx.send("Error accessing Random.org. Please try again later.")

    @commands.hybrid_command(name = "logitech", description = "see why logitech is the way to go")
    async def logitech(self, ctx):
        await ctx.send("i was asking about why to get razer when they copied logitech. that was all i wanted to know, theres no basis on anything said expect for ""its better"", but sure if 7ms is worth it for shitty QA and having to rma it in 3 months then go ahead. atleast with logitech you can upgrade to the powerplay and have the mouse charge while you play so you never have to worry about it.  ")

    @commands.hybrid_command(name = "razer", description = "see why razer is trash")
    async def razer(self, ctx):
        await ctx.send("razer lost my trust when all i hear are issues online and that they just use gamer marketing to get people buying. like their razer switches which are just different coloured kailh switches")

    @commands.hybrid_command(name = "увлажнение", description = "Если нужно увлажнится")
    async def увлажнение(self, ctx):
        number = random.randint(1, 100)
        mention = ctx.author.mention
        await ctx.send(f"{mention} увлажнился на {number}%")

async def setup(bot):
    cog = Fun(bot)
    await bot.add_cog(cog)
