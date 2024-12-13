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
        # Initialize with default replies in the new format
        self.replies: Dict[str, dict] = {
            "help": {
                "response": "Need help? Use !help to see all available commands!",
                "reactions": ["❓"]
            }
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
        for trigger, reply_data in self.replies.items():
            if trigger.lower() in content:
                # Add reactions
                if "reactions" in reply_data:
                    for reaction in reply_data["reactions"]:
                        try:
                            await message.add_reaction(reaction)
                        except discord.errors.HTTPException:
                            continue  # Skip invalid emoji
                
                # Send text response if it exists
                if "response" in reply_data and reply_data["response"]:
                    # Replace {user} with user mention
                    response = reply_data["response"].replace("{user}", message.author.mention)
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

        self.replies[trigger.lower()] = {
            "response": response,
            "reactions": reaction_list
        }
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
            reply_data = self.replies.pop(trigger)
            self.save_replies()
            
            embed = create_embed(
                title="Auto-Reply Removed",
                description=f"Trigger: {trigger}\nResponse: {reply_data.get('response', 'None')}\nReactions: {' '.join(reply_data.get('reactions', []))}",
                color=discord.Color.red().value
            )
        else:
            embed = create_embed(
                title="Error",
                description=f"Trigger '{trigger}' not found in replies",
                color=discord.Color.red().value
            )
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="addreaction", description="Add a reaction-only trigger")
    @commands.has_permissions(manage_messages=True)
    async def add_reaction_only(self, ctx, trigger: str, reactions: str) -> None:
        """
        Add a new trigger that only adds reactions, no text response
        
        Parameters:
        -----------
        trigger: str
            The word or phrase that will trigger the reactions
        reactions: str
            Comma-separated list of emoji reactions (e.g., "👍,❤️,😊")
        """
        reaction_list = [r.strip() for r in reactions.split(",")]
            
        if not reaction_list:
            await ctx.send("You must provide at least one reaction!")
            return

        self.replies[trigger.lower()] = {
            "response": None,
            "reactions": reaction_list
        }
        self.save_replies()
        
        embed = create_embed(
            title="New Reaction Trigger Added",
            description=f"Trigger: {trigger}\nReactions: {' '.join(reaction_list)}",
            color=discord.Color.green().value
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
        
        for trigger, reply_data in self.replies.items():
            value = f"Response: {reply_data.get('response', 'No text response')}\nReactions: {' '.join(reply_data.get('reactions', []))}"
            embed.add_field(
                name=trigger,
                value=value,
                inline=False
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Replies(bot))