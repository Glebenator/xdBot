# main.py
import os
import logging
import asyncio
import signal

import discord
from discord.ext import commands

from dotenv import load_dotenv

# Load environment variables before importing the configuration module
load_dotenv()

import config

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
            command_prefix=commands.when_mentioned_or(config.settings.prefix),
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
    token = config.settings.discord_token
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set in the environment.")

    bot = DiscordBot()
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    handled_signals = []

    def _request_shutdown(sig: signal.Signals):
        if not stop_event.is_set():
            logger.info("Shutdown signal received from %s. Beginning graceful shutdown...", sig.name)
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: _request_shutdown(s))
            handled_signals.append(sig)
        except (NotImplementedError, RuntimeError):
            logger.debug("Signal handling not supported for %s on this platform.", sig.name)

    bot_task = asyncio.create_task(bot.start(token), name="discord.py:bot.start")
    stop_task = asyncio.create_task(stop_event.wait(), name="discord.py:shutdown.wait")

    try:
        done, pending = await asyncio.wait({bot_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)

        if stop_task in done:
            logger.info("Closing bot connection...")
            await bot.close()
            await bot_task
        else:
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
            await bot_task
    finally:
        for sig in handled_signals:
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError):
                logger.debug("Failed to remove signal handler for %s.", sig.name)

        if not bot.is_closed():
            await bot.close()

        logger.info("Bot shutdown complete.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Bot stopped cleanly.")