"""Start the Discord bot or check its extensions offline."""

import argparse
import ast
import asyncio
import logging
import signal
from pathlib import Path
from tempfile import TemporaryDirectory

import discord
from discord.ext import commands

from config import settings

logger = logging.getLogger(__name__)
COG_DIR = Path(__file__).resolve().parent / "cogs"


class DiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(
            command_prefix=commands.when_mentioned_or(settings.prefix),
            intents=intents,
            help_command=None,
            owner_ids=settings.owner_ids,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, replied_user=False),
        )

    def _set_ready(self, ready: bool) -> None:
        if settings.ready_file is not None:
            if ready:
                settings.ready_file.touch()
            else:
                settings.ready_file.unlink(missing_ok=True)

    async def setup_hook(self) -> None:
        await load_extensions(self)
        commands_synced = await self.tree.sync()
        logger.info("Synced %d slash commands", len(commands_synced))

    async def on_ready(self) -> None:
        self._set_ready(True)
        logger.info("Connected as %s in %d servers", self.user, len(self.guilds))

    async def on_resumed(self) -> None:
        self._set_ready(True)

    async def on_disconnect(self) -> None:
        self._set_ready(False)

    async def close(self) -> None:
        self._set_ready(False)
        await super().close()


def _iter_extension_paths(root: Path | str = COG_DIR) -> list[str]:
    root = Path(root)
    modules = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).with_suffix("")
        if any(part.startswith((".", "__")) for part in relative.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(isinstance(node, ast.AsyncFunctionDef) and node.name == "setup" for node in tree.body):
            modules.append(".".join((root.name, *relative.parts)))
    return modules


async def load_extensions(bot: DiscordBot) -> None:
    extensions = _iter_extension_paths()
    if not extensions:
        raise RuntimeError("No bot extensions found.")
    for extension in extensions:
        await bot.load_extension(extension)
        logger.info("Loaded %s", extension)


async def check_extensions() -> None:
    with TemporaryDirectory(prefix="xdbot-check-") as directory:
        settings.data_dir = Path(directory)
        settings.ready_file = None
        async with DiscordBot() as bot:
            await load_extensions(bot)
            logger.info("Checked %d extensions and %d slash commands", len(bot.extensions), len(bot.tree.get_commands()))


async def main() -> None:
    if not settings.discord_token:
        raise RuntimeError("Set DISCORD_TOKEN before you start the bot.")

    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    signals = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, task.cancel)
            signals.append(sig)
        except NotImplementedError:
            continue

    try:
        async with DiscordBot() as bot:
            bot._set_ready(False)
            await bot.start(settings.discord_token)
    except asyncio.CancelledError:
        logger.info("Bot stopped")
    finally:
        for sig in signals:
            loop.remove_signal_handler(sig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Load extensions without connecting to Discord.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(check_extensions() if args.check else main())
    except KeyboardInterrupt:
        pass
