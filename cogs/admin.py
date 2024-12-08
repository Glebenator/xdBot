# cogs/admin.py
import discord
from discord.ext import commands
import config

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

async def setup(bot):
    await bot.add_cog(Admin(bot))