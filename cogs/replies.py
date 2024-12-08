# cogs/replies.py
import discord
from discord.ext import commands
from typing import Dict, List, Union, Tuple
import json
import os
from utils.helpers import create_embed

class Replies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Structure: {"trigger": ("response", ["reaction1", "reaction2"])}
        self.replies: Dict[str, Tuple[str, List[str]]] = {
            "hello": ("👋 Hey there!", ["👋"]),
            "good morning": ("Good morning! Hope you have a great day!", ["🌅", "☀️"]),
            "good night": ("Good night! Sleep well!", ["🌙", "💤"]),
            "thanks": ("You're welcome! 😊", ["❤️"]),
            "help": ("Need help? Use !help to see all available commands!", ["❓"]),
        }
        self.load_replies()

    def load_replies(self) -> None:
        """Load custom replies from JSON file if it exists"""
        try:
            if os.path.exists('data/replies.json'):
                with open('data/replies.json', 'r') as f:
                    self.replies.update(json.load(f))
        except Exception as e:
            print(f"Error loading replies: {e}")

    def save_replies(self) -> None:
        """Save custom replies to JSON file"""
        try:
            os.makedirs('data', exist_ok=True)
            with open('data/replies.json', 'w') as f:
                json.dump(self.replies, f, indent=4)
        except Exception as e:
            print(f"Error saving replies: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Listen for messages and respond with text and/or reactions"""
        if message.author == self.bot.user:
            return

        content = message.content.lower()
        for trigger, (response, reactions) in self.replies.items():
            if trigger.lower() in content:
                # Add reactions
                for reaction in reactions:
                    try:
                        await message.add_reaction(reaction)
                    except discord.errors.HTTPException:
                        continue  # Skip invalid emoji
                
                # Send text response if it exists
                if response:
                    await message.channel.send(response)
                break

    @commands.hybrid_command(name="addreply", description="Add a new auto-reply trigger with text and/or reactions")
    @commands.has_permissions(manage_messages=True)
    async def add_reply(self, ctx, trigger: str, response: str = None, reactions: str = None) -> None:
        """
        Add a new trigger word with response and/or reactions
        
        Parameters:
        -----------
        trigger: str
            The word or phrase that will trigger the response
        response: str, optional
            The text response to send (can be None if only using reactions)
        reactions: str, optional
            Comma-separated list of emoji reactions (e.g., "👍,❤️,😊")
        """
        reaction_list = []
        if reactions:
            reaction_list = [r.strip() for r in reactions.split(",")]
            
        if not response and not reaction_list:
            await ctx.send("You must provide either a response message or reactions!")
            return

        self.replies[trigger.lower()] = (response, reaction_list)
        self.save_replies()
        
        embed = create_embed(
            title="New Auto-Reply Added",
            description=f"Trigger: {trigger}\nResponse: {response}\nReactions: {' '.join(reaction_list)}",
            color=discord.Color.green().value
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="removereply", description="Remove an auto-reply trigger")
    @commands.has_permissions(manage_messages=True)
    async def remove_reply(self, ctx, trigger: str) -> None:
        """Remove a trigger word and its responses"""
        trigger = trigger.lower()
        if trigger in self.replies:
            response, reactions = self.replies.pop(trigger)
            self.save_replies()
            
            embed = create_embed(
                title="Auto-Reply Removed",
                description=f"Trigger: {trigger}\nResponse: {response}\nReactions: {' '.join(reactions)}",
                color=discord.Color.red().value
            )
        else:
            embed = create_embed(
                title="Error",
                description=f"Trigger '{trigger}' not found in replies",
                color=discord.Color.red().value
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="listreplies", description="List all auto-reply triggers and responses")
    async def list_replies(self, ctx) -> None:
        """List all trigger words and their responses"""
        embed = create_embed(
            title="Auto-Replies List",
            description="Here are all the current auto-replies:",
            color=discord.Color.blue().value
        )
        
        for trigger, (response, reactions) in self.replies.items():
            value = f"Response: {response or 'No text response'}\nReactions: {' '.join(reactions)}"
            embed.add_field(
                name=trigger,
                value=value,
                inline=False
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Replies(bot))