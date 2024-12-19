 # cogs/llm.py
import discord
from discord.ext import commands
from utils.llm_handler import LLMHandler
from utils.helpers import create_embed
from utils.system_promt import get_system_prompt
import os
from typing import Optional
from datetime import datetime

class LLM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        api_key = os.getenv('HF_TOKEN')
        if not api_key:
            raise ValueError("HF_TOKEN not found in environment variables")
        self.llm = LLMHandler(api_key)

    @commands.hybrid_command(
        name="chat",
        description="Chat with the rude bot powered by AI"
    )
    async def chat(self, ctx, *, message: str):
        """Chat with the AI bot with conversation memory"""
        await ctx.defer()
        
        try:
            async with ctx.typing():
                response = await self.llm.generate_response(
                    ctx.author.id,
                    message,
                    get_system_prompt()
                )
            
            if response.startswith("Error:"):
                embed = create_embed(
                    title="Error",
                    description=response,
                    color=discord.Color.red().value
                )
                await ctx.send(embed=embed)
            else:
                if len(response) > 2000:
                    chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    for chunk in chunks:
                        await ctx.send(chunk)
                else:
                    await ctx.send(response)
            
        except Exception as e:
            embed = create_embed(
                title="Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red().value
            )
            await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="clear_chat",
        description="Clear your chat history with the bot"
    )
    async def clear_chat(self, ctx):
        """Clear the conversation history for the user"""
        self.llm.clear_history(ctx.author.id)
        embed = create_embed(
            title="Chat History Cleared",
            description="Your conversation history has been cleared.",
            color=discord.Color.green().value
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="show_history",
        description="Show your chat history with the bot"
    )
    async def show_history(self, ctx):
        """Display the conversation history for the user"""
        history = self.llm.get_history(ctx.author.id)
        
        if not history:
            embed = create_embed(
                title="Chat History",
                description="No chat history found.",
                color=discord.Color.blue().value
            )
            await ctx.send(embed=embed)
            return

        embed = create_embed(
            title="Chat History",
            description="Here's your recent chat history:",
            color=discord.Color.blue().value
        )

        for i, msg in enumerate(history, 1):
            role = "You" if msg["role"] == "user" else "Bot"
            content = msg["content"][:1000] + "..." if len(msg["content"]) > 1000 else msg["content"]
            embed.add_field(
                name=f"{i}. {role}",
                value=content,
                inline=False
            )

        await ctx.send(embed=embed, ephemeral=True)
    
    @commands.hybrid_command(name = "show_prompt", description = "Show the current system prompt")
    async def show_prompt(self, ctx):
        """Display the system prompt to the user"""
        await ctx.send(" ``` " + get_system_prompt() + " ``` ")
        return

async def setup(bot):
    await bot.add_cog(LLM(bot))