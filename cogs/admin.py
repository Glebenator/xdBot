# cogs/admin.py
import logging

import discord
from discord.ext import commands

from utils.db_handler import get_database_handler
from utils.helpers import defer_hybrid

logger = logging.getLogger(__name__)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = get_database_handler()

    @staticmethod
    def _require_guild(ctx) -> int:
        if ctx.guild is None:
            raise commands.NoPrivateMessage("This command can only be used in a server context.")
        return ctx.guild.id

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
        await defer_hybrid(ctx)
        try:
            guild_id = self._require_guild(ctx)
            await self.db.set_total_success(guild_id, user.id, user.display_name, points)
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
        await defer_hybrid(ctx)
        try:
            guild_id = self._require_guild(ctx)
            await self.db.update_user(guild_id, user.id, user.display_name)
            await self.db.add_total_success(guild_id, user.id, points)
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
        await defer_hybrid(ctx)
        try:
            guild_id = self._require_guild(ctx)
            current_points = await self.db.get_total_success(guild_id, user.id)
            new_points = max(0, current_points - points)
            await self.db.set_total_success(guild_id, user.id, user.display_name, new_points)
            points_removed = current_points - new_points
            await ctx.send(f"✅ Removed {points_removed} success points from {user.mention}. New total: {new_points}")

        except Exception as e:
            logger.exception("Error in remove_points command", extra={"user_id": user.id, "guild_id": ctx.guild.id if ctx.guild else None})
            await ctx.send(f"❌ Error removing points: {str(e)}")

    @commands.hybrid_command(
        name="setstreak",
        description="[ADMIN] Set a user's success streak"
    )
    @commands.has_permissions(administrator=True)
    async def set_streak(self, ctx, user: discord.Member, streak: int):
        """Set a user's success streak"""
        await defer_hybrid(ctx)
        try:
            guild_id = self._require_guild(ctx)
            await self.db.set_success_streak(guild_id, user.id, user.display_name, streak)
            await ctx.send(f"✅ Set {user.mention}'s streak to {streak}")
        except Exception as e:
            await ctx.send(f"❌ Error setting streak: {str(e)}")

    @commands.hybrid_command(
        name="resetstats",
        description="[ADMIN] Reset all success stats for a user"
    )
    @commands.has_permissions(administrator=True)
    async def reset_stats(self, ctx, user: discord.Member):
        """Reset all success-related stats for a user"""
        await defer_hybrid(ctx)
        try:
            guild_id = self._require_guild(ctx)
            await self.db.reset_success_stats(guild_id, user.id)
            await self.db.update_user(guild_id, user.id, user.display_name)

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
