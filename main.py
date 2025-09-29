# main.py
import os
import logging
import asyncio

import discord
from discord.ext import commands

import config
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Voice support has been removed from the bot; suppress the optional PyNaCl warning.
discord.VoiceClient.warn_nacl = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(config.PREFIX),
            intents=intents,
            help_command=None  # We can create a custom help command later
        )
        
    async def setup_hook(self):
        await load_extensions(self)
        try:
            await self.tree.sync()
            logger.info("Application commands synced")
        except Exception as exc:
            logger.error("Failed to sync application commands: %s", exc)

    async def on_ready(self):
        if not self.user:
            return
        logger.info("%s has connected to Discord!", self.user)
        logger.info("Bot is in %s guilds", len(self.guilds))
        
        # Set custom status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.streaming,
                name='xdd'
            )
        )

async def load_extensions(bot):
    """Load all extensions (cogs) from the cogs directory including subdirectories."""
    cog_dir = "cogs"  # Adjust if your cogs are in a different directory
    
    logger.info("Loading extensions from %s...", cog_dir)

    extensions_to_load = []
    
    # Walk through the cogs directory and load extensions
    for item in os.listdir(cog_dir):
        item_path = os.path.join(cog_dir, item)
        
        # Skip hidden files/folders and __pycache__
        if item.startswith("__") or item.startswith("."):
            continue
            
        extension_path = None
        
        # Case 1: Item is a Python file
        if os.path.isfile(item_path) and item.endswith('.py'):
            extension_path = f"{cog_dir}.{item[:-3]}"  # Remove the .py extension
            
        # Case 2: Item is a directory with an __init__.py file (module)
        elif os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
            extension_path = f"{cog_dir}.{item}"
        
        # Load the extension if it's valid
        if extension_path and extension_path not in extensions_to_load:
            extensions_to_load.append(extension_path)

    loaded_cogs = 0
    failed_cogs = 0

    for extension_path in sorted(extensions_to_load):
        try:
            await bot.load_extension(extension_path)
            logger.info("✅ Loaded extension: %s", extension_path)
            loaded_cogs += 1
        except commands.errors.ExtensionAlreadyLoaded:
            logger.warning("Extension already loaded: %s", extension_path)
        except Exception as exc:
            logger.error("❌ Failed to load extension %s: %s", extension_path, exc)
            failed_cogs += 1

    logger.info("Extension loading complete. Loaded: %s, Failed: %s", loaded_cogs, failed_cogs)

async def main():
    bot = DiscordBot()
    await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == '__main__':
    asyncio.run(main())