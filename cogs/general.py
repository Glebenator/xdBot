# cogs/general.py
import discord
import random
from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

    @commands.hybrid_command(name="ping", description="Check bot's latency")
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'Pong! Latency: {latency}ms')

    @commands.hybrid_command(name="help", description="Shows this help message")
    async def help(self, ctx):
        commands_list = list(self.bot.commands)
        chunk_size = 10  # Adjust as needed
        
        # Break commands into chunks
        for i in range(0, len(commands_list), chunk_size):
            chunk = commands_list[i:i + chunk_size]
            embed = discord.Embed(
                title=f"Bot Help (Page {i // chunk_size + 1})",
                description="List of available commands:",
                color=discord.Color.blue()
            )
            
            for command in chunk:
                embed.add_field(
                    name=command.name,
                    value=command.description or "No description available",
                    inline=False
                )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))