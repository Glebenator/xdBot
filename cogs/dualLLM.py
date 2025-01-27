# cogs/llm.py
import discord
from discord.ext import commands
from utils.helpers import create_embed
from utils.system_prompt import get_system_prompt
from utils.llm_handler import LLMHandler  # Original Mixtral handler
from utils.gemini_handler import GeminiHandler
import os
from typing import Optional

class LLMCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Initialize Mixtral handler for /chat command
        mixtral_api_key = os.getenv('HF_TOKEN')
        if not mixtral_api_key:
            raise ValueError("HF_TOKEN not found in environment variables")
        self.mixtral = LLMHandler(mixtral_api_key)
        
        # Initialize Gemini handler for mentions
        gemini_api_key = os.getenv('GOOGLE_TOKEN')
        if not gemini_api_key:
            raise ValueError("GOOGLE_TOKEN not found in environment variables")
        self.gemini = GeminiHandler(gemini_api_key)

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle mentions of the bot using Gemini"""
        if message.author == self.bot.user:
            return
            
        if self.bot.user in message.mentions:
            content = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
            if content:
                async with message.channel.typing():
                    response = await self.gemini.generate_response(
                        message.author.id,
                        content
                    )
                
                if response.startswith("Error:"):
                    embed = create_embed(
                        title="Error",
                        description=response,
                        color=discord.Color.red().value
                    )
                    await message.reply(embed=embed)
                else:
                    if len(response) > 2000:
                        chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                        for i, chunk in enumerate(chunks):
                            if i == 0:
                                await message.reply(chunk)
                            else:
                                await message.channel.send(chunk)
                    else:
                        await message.reply(response)

    @commands.hybrid_command(
        name="chat",
        description="Chat with the rude bot powered by Mixtral AI"
    )
    async def chat(self, ctx, *, message: str):
        """Chat with Mixtral AI with conversation memory"""
        await ctx.defer()
        
        try:
            async with ctx.typing():
                response = await self.mixtral.generate_response(
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
        description="Clear your chat history with both AI models"
    )
    async def clear_chat(self, ctx):
        """Clear the conversation history for both models"""
        self.mixtral.clear_history(ctx.author.id)
        self.gemini.clear_history(ctx.author.id)
        embed = create_embed(
            title="Chat History Cleared",
            description="Your conversation history has been cleared for both AI models.",
            color=discord.Color.green().value
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="show_mixtral_history",
        description="Show your Mixtral chat history"
    )
    async def show_mixtral_history(self, ctx):
        """Display the Mixtral conversation history"""
        history = self.mixtral.get_history(ctx.author.id)
        await self._send_history_embed(ctx, history, "Mixtral")

    @commands.hybrid_command(
        name="show_gemini_history",
        description="Show your Gemini chat history"
    )
    async def show_gemini_history(self, ctx):
        """Display the Gemini conversation history"""
        history = self.gemini.get_history(ctx.author.id)
        await self._send_history_embed(ctx, history, "Gemini")

    async def _send_history_embed(self, ctx, history, model_name):
        """Helper method to send history embed"""
        if not history:
            embed = create_embed(
                title=f"{model_name} Chat History",
                description="No chat history found.",
                color=discord.Color.blue().value
            )
            await ctx.send(embed=embed)
            return

        embed = create_embed(
            title=f"{model_name} Chat History",
            description=f"Here's your recent {model_name} chat history:",
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
    
    @commands.hybrid_command(
        name="show_prompt", 
        description="Show the current system prompt"
    )
    async def show_prompt(self, ctx):
        """Display the system prompt to the user"""
        await ctx.send("```" + get_system_prompt() + "```")

async def setup(bot):
    await bot.add_cog(LLMCog(bot))