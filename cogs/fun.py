# cogs/fun.py
import discord
from discord.ext import commands
from utils.helpers import create_embed
from utils.db_handler import DatabaseHandler
from utils.rng import RandomOrgRNG
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
# Load environment variables
load_dotenv()

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseHandler()
        api_key = os.getenv('RANDOM_ORG_KEY')
        if not api_key:
            raise ValueError("RANDOM_ORG_KEY not found in environment variables")
        self.rng = RandomOrgRNG(api_key)

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        await self.rng.close()

    @commands.hybrid_command(name="roll", description="Roll a random number using Random.org")
    async def roll(self, ctx, max_num: int = 100):
        """Roll a random number between 1 and max_num using true randomness from Random.org"""
        await ctx.defer()  # Acknowledge command while we wait for Random.org
        
        # Update database
        self.db.update_user(ctx.author.id, ctx.author.name)
        
        try:
            number = await self.rng.randint(1, max_num)
            self.db.log_command_usage(ctx.author.id, "roll", roll_value=number)
            await ctx.send(f"{ctx.author.mention} rolled {number} 🎲")
        except Exception as e:
            await ctx.send("Error accessing Random.org. Please try again later.")

    @commands.hybrid_command(name="успех", description="See how successful you are today using true randomness (once per 12h)")
    async def success(self, ctx):
        await ctx.defer()  # Acknowledge command while we wait for Random.org
        
        user_id = ctx.author.id
        current_time = datetime.now()
        
        # Update user record
        self.db.update_user(user_id, ctx.author.name)
        
        # Check cooldown
        last_used = self.db.get_command_cooldown(user_id, "успех")
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
            # Generate success message using Random.org
            number = await self.rng.randint(1, 100)
            mention = ctx.author.mention
            
            # Map number ranges to success levels (1-6)
            if number < 5:
                message = f"{mention} 📉 Massive anti-success"
                success_level = 1
            elif number < 10:
                message = f"{mention} 🗑️ garbage success"
                success_level = 2
            elif number < 50:
                message = f"{mention} ❌ is not successful today"
                success_level = 3
            elif number < 75:
                message = f"{mention} 📈 is somewhat successful today"
                success_level = 4
            elif number < 90:
                message = f"{mention} 💰 is very successful today"
                success_level = 5
            else:
                message = f"{mention} 🌟 IS A MASSIVE SUCCESSFUL BUSINESSMAN"
                success_level = 6

            # Update database
            self.db.update_command_cooldown(user_id, "успех")
            self.db.log_command_usage(user_id, "успех", success_level=success_level)
            
            await ctx.send(message)
            
        except Exception as e:
            await ctx.send("Error accessing Random.org. Please try again later.")

    @commands.hybrid_command(
        name="топ",
        description="View the success level leaderboard"
    )
    async def success_leaderboard(self, ctx):
        """View the успех command leaderboard"""
        leaderboard_data = self.db.get_success_leaderboard()
        
        if not leaderboard_data:
            await ctx.send("No успех data available yet!")
            return

        embed = create_embed(
            title="💫 Success Leaderboard 💫",
            description="Top successful businessmen:",
            color=discord.Color.gold().value
        )

        # Format leaderboard entries
        for i, entry in enumerate(leaderboard_data, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👔"
            value = (
                f"Highest success: **{entry['highest_success']}**\n"
                f"Average success: {entry['avg_success']:.1f}\n"
                f"Total attempts: {entry['total_attempts']}"
            )
            embed.add_field(
                name=f"{medal} #{i} {entry['username']}",
                value=value,
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="stats", description="View your command usage statistics")
    async def stats(self, ctx):
        """View your command usage statistics"""
        stats = self.db.get_user_stats(ctx.author.id)
        
        embed = create_embed(
            title=f"Stats for {ctx.author.name}",
            color=discord.Color.green().value
        )

        # Command usage counts
        command_counts = stats['command_counts']
        commands_str = "\n".join(f"{cmd}: {count} times" 
                               for cmd, count in command_counts.items())
        embed.add_field(
            name="Command Usage",
            value=commands_str or "No commands used yet",
            inline=False
        )

        # Success command stats
        success_stats = stats['success_stats']
        if success_stats['total_successes']:
            success_str = (
                f"Total checks: {success_stats['total_successes']}\n"
                f"Average level: {success_stats['avg_success']:.2f}\n"
                f"Highest level: {success_stats['max_success']}"
            )
            embed.add_field(
                name="Success Stats",
                value=success_str,
                inline=False
            )

        # Roll command stats
        roll_stats = stats['roll_stats']
        if roll_stats['total_rolls']:
            roll_str = (
                f"Total rolls: {roll_stats['total_rolls']}\n"
                f"Average roll: {roll_stats['avg_roll']:.2f}\n"
                f"Highest roll: {roll_stats['max_roll']}"
            )
            embed.add_field(
                name="Roll Stats",
                value=roll_str,
                inline=False
            )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Fun(bot))