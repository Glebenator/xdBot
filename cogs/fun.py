# cogs/fun.py
import discord
from discord.ext import commands
from discord.ui import View, Button
from utils.helpers import create_embed
from utils.db_handler import DatabaseHandler
from utils.rng import RandomOrgRNG
from datetime import datetime, timedelta
import logging
import random
import os

class SuccessView(View):
    def __init__(self):
        super().__init__(timeout=None)  # Buttons won't timeout
        
        # Add reroll button - no need to store user ID in custom_id anymore
        reroll_button = Button(
            style=discord.ButtonStyle.primary,
            label="Reroll",
            emoji="🎲",
            custom_id="success_reroll"
        )
        self.add_item(reroll_button)

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

    async def handle_success_roll(self, ctx, interaction=None) -> tuple[str, int]:
        """Handle the success roll logic"""
        try:
            number = await self.rng.randint(1, 100)
            mention = ctx.author.mention    
            # Log the roll result
            logging.info(f"Success roll for {ctx.author.name}#{ctx.author.discriminator} (ID: {ctx.author.id}): {number}")
            
            message_part, success_level = await self.process_success_roll(number)
            
            user = interaction.user if interaction else ctx.author
            message = f"{user.mention} {message_part}"
            
            # Update database
            self.db.log_command_usage(user.id, "успех", success_level=success_level)
            self.db.update_total_success(user.id, success_level)
            
            # Update streak and get streak info
            streak_info = self.db.update_success_streak(user.id)
            
            if streak_info['streak_continued']:
                message += f"\n🔥 Streak continued! Current streak: {streak_info['current_streak']} days"
                
                # Unlock reroll ability at 7 day streak
                if streak_info['current_streak'] == 7:
                    self.db.unlock_reroll_ability(user.id)
                    message += "\n🎁 Congratulations! You've unlocked the reroll ability!"
                    
            elif streak_info['streak_reset']:
                message += f"\n❌ Streak reset! Starting new streak!"
                
            return message, success_level
        except Exception as e:
            logging.error(f"Error processing success roll: {str(e)}")
            raise

    @commands.hybrid_command(name="успех", description="See how successful you are today using true randomness (once per 12h)")
    async def success(self, ctx):
        """Check your daily success level"""
        await ctx.defer()
        
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
            message, success_level = await self.handle_success_roll(ctx)
            
            # Update cooldown
            self.db.update_command_cooldown(user_id, "успех")
            
            # Check if user has reroll ability
            view = None
            if self.db.has_reroll_ability(user_id):
                view = SuccessView()
            
            await ctx.send(message, view=view)
            
        except Exception as e:
            await ctx.send("Error accessing Random.org. Please try again later.")

    async def on_button_click(self, interaction: discord.Interaction):
        """Handle button clicks for success command"""
        # First check if this is a button interaction
        if interaction.type != discord.InteractionType.component:
            return
            
        # Safely get custom_id
        if not interaction.data or 'custom_id' not in interaction.data:
            return
            
        # Check if this is a success reroll button
        if interaction.data['custom_id'] != "success_reroll":
            return
            
        try:
            # Get the original user from the message content
            message_content = interaction.message.content
            if not message_content:
                await interaction.response.send_message(
                    "Could not find the original message content.", 
                    ephemeral=True
                )
                return
                
            # Extract user ID from message content (format: "<@userId> rest of message")
            try:
                first_word = message_content.split()[0]
                if not first_word.startswith('<@') or not first_word.endswith('>'):
                    await interaction.response.send_message(
                        "Could not identify the original roll owner.", 
                        ephemeral=True
                    )
                    return
                    
                mentioned_user_id = int(first_word.strip('<@!>'))  # Handle both <@id> and <@!id> formats
            except (IndexError, ValueError) as e:
                await interaction.response.send_message(
                    "Could not identify the original roll owner.", 
                    ephemeral=True
                )
                print(f"Error parsing user ID: {str(e)}, message content: {message_content}")
                return

            # Check if this is the user's own success roll
            if interaction.user.id != mentioned_user_id:
                await interaction.response.send_message(
                    "You can only reroll your own success check!", 
                    ephemeral=True
                )
                return

            # Check if user has reroll ability
            if not self.db.has_reroll_ability(interaction.user.id):
                await interaction.response.send_message(
                    "You don't have the reroll ability!", 
                    ephemeral=True
                )
                return

            # Check cooldown
            last_used = self.db.get_command_cooldown(interaction.user.id, "успех")
            if not last_used:
                await interaction.response.send_message(
                    "No active успех roll to reroll!", 
                    ephemeral=True
                )
                return

            # Check if still within cooldown period
            current_time = datetime.now()
            if current_time > last_used + timedelta(hours=12):
                await interaction.response.send_message(
                    "This success check has expired! Use !успех for a new roll.", 
                    ephemeral=True
                )
                return
                
            # Process reroll
            await interaction.response.defer()
            
            try:
                message, success_level = await self.handle_success_roll(None, interaction)
                
                # Update the original message with new roll and remove the button
                await interaction.message.edit(content=message, view=None)
            except Exception as e:
                await interaction.followup.send(
                    "Error generating new roll. Please try again later.", 
                    ephemeral=True
                )
                print(f"Error in reroll generation: {str(e)}")
                
        except discord.errors.Forbidden as e:
            await interaction.response.send_message(
                "I don't have permission to modify that message.", 
                ephemeral=True
            )
        except discord.errors.NotFound:
            await interaction.response.send_message(
                "The original message was not found.", 
                ephemeral=True
            )
        except discord.errors.HTTPException as e:
            await interaction.response.send_message(
                "Failed to process reroll. Please try again later.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "An unexpected error occurred. Please try again later.",
                ephemeral=True
            )
            print(f"Unexpected error in reroll button handler: {str(e)}")

    @commands.hybrid_command(
    name="топ",
    description="View the success leaderboard"
)
    async def success_leaderboard(self, ctx):
        """View the успех command leaderboard"""
        leaderboard_data = self.db.get_success_leaderboard()
        
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
            has_reroll = entry.get('has_reroll_ability', False)
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
            if has_reroll:
                achievements.append("🎲 Reroll Master")
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
        stats = self.db.get_success_stats(ctx.author.id)
        
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
        abilities = []
        if stats['has_reroll_ability']:
            abilities.append("🎲 Reroll Ability")
            
        streak_text = f"🔥 {stats['success_streak']} days"
        if stats['success_streak'] >= 7:
            streak_text += "\n(Reroll Unlocked!)"
            
        embed.add_field(
            name="Current Streak",
            value=streak_text,
            inline=True
        )
        
        if abilities:
            embed.add_field(
                name="Unlocked Abilities",
                value="\n".join(abilities),
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
        await ctx.defer()  # Acknowledge command while we wait for Random.org
        
        # Update database
        self.db.update_user(ctx.author.id, ctx.author.name)
        
        try:
            number = await self.rng.randint(1, max_num)
            self.db.log_command_usage(ctx.author.id, "roll", roll_value=number)
            await ctx.send(f"{ctx.author.mention} rolled {number} 🎲")
        except Exception as e:
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
    bot.add_listener(cog.on_button_click, "on_interaction")
    await bot.add_cog(cog)