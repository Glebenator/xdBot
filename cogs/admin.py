# cogs/admin.py
import discord
from discord.ext import commands
from utils.db_handler import DatabaseHandler
import config

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = DatabaseHandler()  # Initialize database handler

    @commands.command(name="reload", description="[ADMIN] Reload a specific cog")
    @commands.is_owner()
    async def reload(self, ctx, extension):
        """Reload a specific cog"""
        try:
            await self.bot.reload_extension(f'cogs.{extension}')
            await ctx.send(f'🔄 Reloaded {extension}')
        except Exception as e:
            await ctx.send(f'❌ Error reloading {extension}: {str(e)}')

    @commands.command(name="sync", description="[ADMIN] Sync slash commands")
    @commands.is_owner()
    async def sync(self, ctx):
        """Sync slash commands"""
        try:
            await self.bot.tree.sync()
            await ctx.send("✅ Successfully synced slash commands")
        except Exception as e:
            await ctx.send(f"❌ Error syncing slash commands: {str(e)}")

    @commands.hybrid_command(
        name="setpoints",
        description="[ADMIN] Set a user's success points"
    )
    @commands.has_permissions(administrator=True)
    async def set_points(self, ctx, user: discord.Member, points: int):
        """Set a user's total success points"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (user_id, username, total_success)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    total_success = ?
            ''', (user.id, user.name, points, points))
            
            conn.commit()
            conn.close()
            
            await ctx.send(f"✅ Set {user.mention}'s success points to {points}")
        except Exception as e:
            await ctx.send(f"❌ Error setting points: {str(e)}")

    @commands.hybrid_command(
        name="addpoints",
        description="[ADMIN] Add success points to a user"
    )
    @commands.has_permissions(administrator=True)
    async def add_points(self, ctx, user: discord.Member, points: int):
        """Add success points to a user"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (user_id, username, total_success)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    total_success = COALESCE(total_success, 0) + ?
            ''', (user.id, user.name, points, points))
            
            conn.commit()
            conn.close()
            
            await ctx.send(f"✅ Added {points} success points to {user.mention}")
        except Exception as e:
            await ctx.send(f"❌ Error adding points: {str(e)}")

    @commands.hybrid_command(
        name="removepoints",
        description="[ADMIN] Remove success points from a user"
    )
    @commands.has_permissions(administrator=True)
    async def remove_points(self, ctx, user: discord.Member, points: int):
        """Remove success points from a user"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Get current points
            cursor.execute('''
                SELECT total_success 
                FROM users 
                WHERE user_id = ?
            ''', (user.id,))
            
            result = cursor.fetchone()
            current_points = result['total_success'] if result else 0
            
            # Calculate new points (don't go below 0)
            new_points = max(0, current_points - points)
            
            # Update points
            cursor.execute('''
                INSERT INTO users (user_id, username, total_success)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    total_success = ?
            ''', (user.id, user.name, new_points, new_points))
            
            conn.commit()
            conn.close()
            
            # Calculate actual points removed
            points_removed = current_points - new_points
            await ctx.send(f"✅ Removed {points_removed} success points from {user.mention}. New total: {new_points}")
            
        except Exception as e:
            print(f"Error in remove_points: {str(e)}")
            await ctx.send(f"❌ Error removing points: {str(e)}")

    @commands.hybrid_command(
        name="setstreak",
        description="[ADMIN] Set a user's success streak"
    )
    @commands.has_permissions(administrator=True)
    async def set_streak(self, ctx, user: discord.Member, streak: int):
        """Set a user's success streak"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO users (user_id, username, success_streak)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    success_streak = ?
            ''', (user.id, user.name, streak, streak))
            
            conn.commit()
            await ctx.send(f"✅ Set {user.mention}'s streak to {streak}")

            conn.close()
        except Exception as e:
            await ctx.send(f"❌ Error setting streak: {str(e)}")

    @commands.hybrid_command(
        name="resetstats",
        description="[ADMIN] Reset all success stats for a user"
    )
    @commands.has_permissions(administrator=True)
    async def reset_stats(self, ctx, user: discord.Member):
        """Reset all success-related stats for a user"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Reset all success-related fields
            cursor.execute('''
                UPDATE users
                SET total_success = 0,
                    success_streak = 0
                WHERE user_id = ?
            ''', (user.id,))
            
            # Clean up command usage history
            cursor.execute('''
                DELETE FROM command_usage
                WHERE user_id = ? AND command_name = 'успех'
            ''', (user.id,))
            
            conn.commit()
            conn.close()
            
            await ctx.send(f"✅ Reset all success stats for {user.mention}")
        except Exception as e:
            await ctx.send(f"❌ Error resetting stats: {str(e)}")

    # Error handlers for the admin commands
    @set_points.error
    @add_points.error
    @remove_points.error
    @set_streak.error
    @reset_stats.error
    async def admin_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command!")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ User not found!")
        else:
            await ctx.send(f"❌ An error occurred: {str(error)}")

async def setup(bot):
    await bot.add_cog(Admin(bot))