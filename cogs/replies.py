"""Manage auto-replies for each server."""

import logging
from pathlib import Path

import discord
from discord.ext import commands

from utils.db_handler import get_database_handler
from utils.guild_rules import GuildRules, read_rule_defaults
from utils.helpers import defer_hybrid

logger = logging.getLogger(__name__)


class Replies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        root = Path(__file__).resolve().parent.parent
        bundled = root / "defaults" / "replies.json"
        if not bundled.is_file():
            bundled = root / "data" / "replies.json"
        legacy = read_rule_defaults("replies.json", bundled) or {}
        defaults = {trigger.casefold(): rule for trigger, rule in legacy.items() if trigger.strip()}
        self.rules = GuildRules(get_database_handler(), "replies", defaults)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        content = message.content.casefold()
        if content == "ah":
            await message.channel.send("Whatever")
            return
        if message.guild is None or not content or (await self.bot.get_context(message)).valid:
            return
        for trigger, rule in (await self.rules.get(message.guild.id)).items():
            if trigger not in content:
                continue
            for emoji in rule.get("reactions", []):
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    logger.debug("Could not add an auto-reply reaction", exc_info=True)
            response = rule.get("response")
            if response:
                mentions = discord.AllowedMentions(
                    everyone=False, roles=False, users=[message.author], replied_user=False
                )
                await message.channel.send(
                    response.replace("{user}", message.author.mention)[:2000],
                    allowed_mentions=mentions,
                )
            return

    async def _set_reply(self, ctx, trigger, response, reactions):
        await defer_hybrid(ctx)
        trigger = trigger.strip().casefold()
        response = (response or "").strip()
        emoji = [item.strip() for item in (reactions or "").split(",") if item.strip()]
        if not 1 <= len(trigger) <= 100:
            await ctx.send("Enter a trigger with 1 to 100 characters.")
            return
        if len(response) > 1500 or len(emoji) > 10:
            await ctx.send("Use up to 1,500 response characters and 10 reactions.")
            return
        if not (response or emoji):
            await ctx.send("Enter a response or at least one reaction.")
            return
        await self.rules.set(ctx.guild.id, trigger, {"response": response, "reactions": emoji})
        await ctx.send("Auto-reply saved.")

    @commands.hybrid_command(name="addreply", description="Save an auto-reply trigger")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def add_reply(self, ctx, trigger: str, response: str | None = None, reactions: str | None = None):
        await self._set_reply(ctx, trigger, response, reactions)

    @commands.hybrid_command(name="addreaction", description="Save a reaction-only trigger")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def add_reaction_only(self, ctx, trigger: str, reactions: str):
        await self._set_reply(ctx, trigger, None, reactions)

    @commands.hybrid_command(name="removereply", description="Remove an auto-reply trigger")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def remove_reply(self, ctx, trigger: str):
        await defer_hybrid(ctx)
        removed = await self.rules.set(ctx.guild.id, trigger.strip().casefold(), None)
        await ctx.send("Auto-reply removed." if removed else "Trigger not found.")

    @commands.hybrid_command(name="listreplies", description="List the auto-replies for this server")
    @commands.guild_only()
    async def list_replies(self, ctx):
        await defer_hybrid(ctx)
        rules = await self.rules.get(ctx.guild.id)
        if not rules:
            await ctx.send("This server has no auto-replies.")
            return
        items = list(rules.items())
        for start in range(0, len(items), 4):
            embed = discord.Embed(title="Auto-Replies", color=discord.Color.blue())
            for trigger, rule in items[start:start + 4]:
                response = rule.get("response") or "No text response"
                emoji = " ".join(rule.get("reactions", []))
                embed.add_field(name=trigger[:256], value=f"{response}\n{emoji}"[:1024], inline=False)
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Replies(bot))
