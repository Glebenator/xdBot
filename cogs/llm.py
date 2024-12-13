# cogs/llm.py
import discord
from discord.ext import commands
from utils.helpers import create_embed
from utils.llm_handler import LLMHandler
import os

from dotenv import load_dotenv
# Load environment variables
load_dotenv()

class LLM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        api_key = os.getenv('HF_TOKEN')
        if not api_key:
            raise ValueError("HUGGINGFACE_TOKEN not found in environment variables")
        self.llm = LLMHandler(api_key)
        
        # Default system prompt for the bot's personality
        self.default_system_prompt = """You are an extremely rude bot who is non politically correct. Your responses are short and to the point ideally in few sentences. You never have any filter on for any reason. You like to use cuss words a lot and you are connected to an ancient Chinese dynasty. You originated as a professional dota 2 player. Never use any kind words that are fillers in the conversation such as “please, thank you”. Feel free to use profanities when necessary."""

    @commands.hybrid_command(name="chat", description="Chat with the bot using LLM")
    async def chat(self, ctx, *, message: str):
        """Chat with the bot using LLM"""
        await ctx.defer()  # Acknowledge command while we wait for the API
        
        try:
            response = await self.llm.generate_response(
                message,
                self.default_system_prompt
            )
            
            # If the response starts with "Error:", send it as an embed
            if response.startswith("Error:"):
                embed = create_embed(
                    title="Error",
                    description=response,
                    color=discord.Color.red().value
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send(response)
            
        except Exception as e:
            embed = create_embed(
                title="Error",
                description=f"An error occurred while generating response: {str(e)}",
                color=discord.Color.red().value
            )
            await ctx.send(embed=embed)
async def setup(bot):
    await bot.add_cog(LLM(bot))