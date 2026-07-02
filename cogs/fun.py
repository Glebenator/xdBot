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
                "RANDOM_ORG_KEY is not configured; falling back to local pseudo-random numbers."
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

    async def process_success_roll(self, number: int) -> tuple[str, int]:
        """Process a success roll and return the message and success level"""
        if number < 5:
            return "📉 Massive anti-success", 1
        elif number < 10:
            return "🗑️ garbage success", 2
        elif number < 50:
            return "❌ is not successful today", 3
        elif number < 75:
            return "📈 is somewhat successful today", 4
        elif number < 90:
            return "💰 is very successful today", 5
        else:
            return "🌟 IS A MASSIVE SUCCESSFUL BUSINESSMAN", 6

    async def handle_success_roll(self, ctx, guild_id: int, interaction=None) -> tuple[str, int]:
        """Handle the success roll logic"""
        try:
            number = await self.rng.randint(1, 100)
            # Log the roll result
            logging.info(f"Success roll for {ctx.author.name}#{ctx.author.discriminator} (ID: {ctx.author.id}): {number}")

            message_part, success_level = await self.process_success_roll(number)

            user = interaction.user if interaction else ctx.author
            message = f"{user.mention} {message_part}"

            # Update database
            await self.db.log_command_usage(
                guild_id,
                user.id,
                "успех",
                success_level=success_level
            )
            await self.db.add_total_success(
                guild_id,
                user.id,
                success_level
            )

            streak_info = await self.db.update_success_streak(
                guild_id,
                user.id
            )

            if streak_info['streak_continued']:
                message += f"\n🔥 Streak continued! Current streak: {streak_info['current_streak']} days"
            elif streak_info['streak_reset']:
                message += "\n❌ Streak reset! Starting new streak!"

            if not self.random_org_enabled:
                message += "\nℹ️ True randomness unavailable; using fallback RNG until a Random.org key is configured."

            return message, success_level
        except Exception as e:
            logging.error(f"Error processing success roll: {str(e)}")
            raise

    @commands.hybrid_command(name="успех", description="See how successful you are today using true randomness (once per 12h)")
    async def success(self, ctx):
        """Check your daily success level"""
        await defer_hybrid(ctx)

        guild_id = self._require_guild(ctx)
        user_id = ctx.author.id
        current_time = datetime.now()

        # Update user record
        await self.db.update_user(guild_id, user_id, ctx.author.name)

        # Check cooldown
        last_used = await self.db.get_command_cooldown(
            guild_id,
            user_id,
            "успех"
        )
        if last_used:
            next_available = last_used + timedelta(hours=12)
            if current_time < next_available:
                time_remaining = next_available - current_time
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)

                embed = create_embed(
                    title="Command on Cooldown ⏳",
                    description=f"You can check your success again in {hours} hours and {minutes} minutes.",
                    color=discord.Color.red().value
                )
                await ctx.send(embed=embed)
                return

        try:
            # Record exact execution time
            await self.db.record_command_execution(
                guild_id,
                user_id,
                "успех"
            )

            message, success_level = await self.handle_success_roll(ctx, guild_id)

            await self.db.update_command_cooldown(
                guild_id,
                user_id,
                "успех"
            )
            await ctx.send(message)

        except Exception:
            await ctx.send("Error accessing Random.org. Please try again later.")

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

    @commands.hybrid_command(name="roll", description="Roll a random number using Random.org")
    async def roll(self, ctx, max_num: int = 100):
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
