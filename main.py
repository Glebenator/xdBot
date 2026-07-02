# main.py
import ast
import asyncio
import logging
import os
import signal

import discord
from discord.ext import commands

import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Set detailed logging for LLM and search tool operations
# Change to DEBUG to see full API requests/responses
llm_log_level = os.getenv('LLM_LOG_LEVEL', 'INFO').upper()
logging.getLogger('utils.ollama_handler').setLevel(getattr(logging, llm_log_level, logging.INFO))
logging.getLogger('utils.search_tool').setLevel(getattr(logging, llm_log_level, logging.INFO))

# Reduce noise from Discord and aiohttp
logging.getLogger('discord.http').setLevel(logging.WARNING)
logging.getLogger('discord.gateway').setLevel(logging.WARNING)
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True  # Enable voice state tracking for music

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

def _module_has_setup(source_path: str) -> bool:
    try:
        with open(source_path, "r", encoding="utf-8") as handle:
            module_ast = ast.parse(handle.read(), filename=source_path)
    except (OSError, SyntaxError) as exc:
        logger.warning("Skipping %s due to parse error: %s", source_path, exc)
        return False

    for node in module_ast.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "setup":
            return True
    return False


def _iter_extension_paths(root: str) -> list[str]:
    extensions: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not d.startswith("__")]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            if filename.startswith("__"):
                continue

            full_path = os.path.join(dirpath, filename)
            if not _module_has_setup(full_path):
                logger.debug("Skipping %s as it lacks an async setup", full_path)
                continue
            rel_path = os.path.relpath(full_path, root)
            module = rel_path[:-3].replace(os.sep, ".")  # strip .py
            extensions.append(f"{root}.{module}")
    return extensions


async def load_extensions(bot):
    """Load all extensions (cogs) from the cogs directory including subpackages."""
    cog_dir = "cogs"

    logger.info("Loading extensions from %s...", cog_dir)

    try:
        extensions_to_load = sorted(set(_iter_extension_paths(cog_dir)))
    except FileNotFoundError:
        logger.error("Cog directory %s was not found. No extensions loaded.", cog_dir)
        return

    loaded_cogs = 0
    failed_cogs = 0

    for extension_path in extensions_to_load:
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
