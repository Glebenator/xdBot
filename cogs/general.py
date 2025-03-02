# cogs/general.py
import discord
import random
from discord.ext import commands
import config

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    def get_command_category(self, command):
        """Determine the category of a command based on its cog or name"""
        if not command.cog:
            return "General"
            
        cog_name = command.cog.__class__.__name__
        if cog_name == "Fun":
            return "Fun & Games"
        elif cog_name == "Moderation":
            return "Moderation"
        elif cog_name == "Admin":
            return "Admin"
        elif cog_name == "Voice":
            return "Voice & Music"
        elif cog_name == "Replies":
            return "Auto-Replies"
        elif cog_name == "LLM":
            return "Chat"
        else:
            return "Misc"
        
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

    @commands.hybrid_command(name="ping", description="Check bot's latency")
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f'Pong! Latency: {latency}ms')

    @commands.hybrid_command(name="help", description="Shows this help message")
    async def help(self, ctx, category_num: int = None):
        """Shows help information, optionally filtered by category number"""
        
        # Get all commands and their categories
        categories = {}
        for command in self.bot.commands:
            cmd_category = self.get_command_category(command)
            if cmd_category not in categories:
                categories[cmd_category] = []
            categories[cmd_category].append(command)

        # Convert to sorted list for consistent numbering
        category_list = sorted(categories.items())

        if category_num is not None and 1 <= category_num <= len(category_list):
            # Show specific category
            category, commands = category_list[category_num - 1]
            embed = discord.Embed(
                title=f"{category} Commands",
                description=f"List of {category.lower()} commands:",
                color=discord.Color.blue()
            )
            
            for command in sorted(commands, key=lambda x: x.name):
                embed.add_field(
                    name=f"{config.PREFIX}{command.name}",
                    value=command.description or "No description available",
                    inline=False
                )
            
            footer_text = f"Type {config.PREFIX}help to see all categories"
            embed.set_footer(text=footer_text)
            await ctx.send(embed=embed)
            
        else:
            # Show category overview
            embed = discord.Embed(
                title="Bot Help",
                description="Choose a category number to view specific commands:",
                color=discord.Color.blue()
            )
            
            for idx, (category, commands) in enumerate(category_list, 1):
                embed.add_field(
                    name=f"{idx}. {category} ({len(commands)})",
                    value=f"Use `{config.PREFIX}help {idx}` to view commands",
                    inline=True
                )
                
            footer_text = f"Example: {config.PREFIX}help 1"
            embed.set_footer(text=footer_text)
            
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))