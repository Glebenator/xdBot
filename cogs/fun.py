# cogs/fun.py
import discord
from discord.ext import commands
import random
from utils.helpers import create_embed

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="roll", description="Roll a random number")
    async def roll(self, ctx, max_num: int = 100):
        """
        Roll a random number between 1 and max_num
        
        Parameters:
        -----------
        max_num: int, optional
            The maximum number to roll (default: 100)
        """
        # Get different variants of the user's name
        name = ctx.author.name  # Their username
        display_name = ctx.author.display_name  # Their server nickname if set, otherwise username
        mention = ctx.author.mention  # Mentions/tags the user with @

        # Generate random number
        number = random.randint(1, max_num)
        
        # You can use any of the name variants:
        # await ctx.send(f"{name} rolled {number}")  # Uses username
        # await ctx.send(f"{mention} rolled {number}")  # Tags the user with @
        await ctx.send(f"{mention} rolled {number}")  # Uses their server nickname

    @commands.hybrid_command(name = "logitech", description = "see why logitech is the way to go")
    async def logitech(self, ctx):
        await ctx.send("i was asking about why to get razer when they copied logitech. that was all i wanted to know, theres no basis on anything said expect for ""its better"", but sure if 7ms is worth it for shitty QA and having to rma it in 3 months then go ahead. atleast with logitech you can upgrade to the powerplay and have the mouse charge while you play so you never have to worry about it.  ")

    @commands.hybrid_command(name = "razer", description = "see why razer is trash")
    async def razer(self, ctx):
        await ctx.send("razer lost my trust when all i hear are issues online and that they just use gamer marketing to get people buying. like their razer switches which are just different coloured kailh switches")

    @commands.hybrid_command(name = "успех", description = "see how successful you are today")
    async def success(self, ctx):
        number = random.randint(1, 100)
        display_name = ctx.author.display_name
        mention = ctx.author.mention  # Mentions/tags the user with @
        if number < 5:
            await ctx.send("Massive anit-success")
        elif number < 10:
            await ctx.send("gargabe success")
        elif number < 50:
            await ctx.send(f"{display_name} is not successful today")
        elif number < 75:
            await ctx.send(f"{display_name} is somewhat successful today")
        elif number < 90:
            await ctx.send(f"{display_name} is very successful today")
        elif number < 100:
            await ctx.send(f"{display_name} IS A MASSIVE SUCCESSFULL BUSINESSMAN")
        
    @commands.hybrid_command(name = "увлажнение", description = "Если нужно увлажнится")
    async def увлажнение(self, ctx):
        number = random.randint(1, 100)
        display_name = ctx.author.display_name
        await ctx.send(f"{mention} увлажнился на {number}%")
async def setup(bot):
    await bot.add_cog(Fun(bot))