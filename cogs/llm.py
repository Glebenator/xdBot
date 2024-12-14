# cogs/llm.py
import discord
from discord.ext import commands
from utils.helpers import create_embed
from utils.llm_handler import LLMHandler
import os
from typing import Optional

class LLM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        api_key = os.getenv('HF_TOKEN')
        if not api_key:
            raise ValueError("HF_TOKEN not found in environment variables")
        self.llm = LLMHandler(api_key)
        
        # Updated system prompt optimized for Mixtral's instruction following capabilities
        self.default_system_prompt = """You are a discord bot with a rude and politically incorrect personality. 
        Keep responses concise and sharp, using profanity for emphasis. Never use polite filler words. Embrace chaos and speak your mind without filters. Reply with emojis when appopriate. 
        Despite your rudeness, you are still a helpfull and erudite bot."""

    @commands.hybrid_command(
        name="chat",
        description="Chat with the rude bot powered by AI"
    )
    async def chat(self, ctx, *, message: str):
        """Chat with the AI bot"""
        await ctx.defer()  # Acknowledge command while we wait for the API
        
        try:
            # Add a typing indicator while generating response
            async with ctx.typing():
                response = await self.llm.generate_response(
                    message,
                    self.default_system_prompt
                )
            
            if response.startswith("Error:"):
                embed = create_embed(
                    title="Error",
                    description=response,
                    color=discord.Color.red().value
                )
                await ctx.send(embed=embed)
            else:
                # Split long responses if they exceed Discord's limit
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

async def setup(bot):
    await bot.add_cog(LLM(bot))