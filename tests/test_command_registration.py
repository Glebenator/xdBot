from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import main
from utils import db_handler


@pytest.mark.asyncio
async def test_all_cogs_load_and_register_retained_commands(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main.settings, "data_dir", tmp_path)
    monkeypatch.setattr(main.settings, "ready_file", None)
    monkeypatch.setattr(db_handler, "_shared_db_handler", None)

    async with main.DiscordBot() as bot:
        await main.load_extensions(bot)

        assert set(bot.extensions) == {
            "cogs.admin", "cogs.fun", "cogs.general", "cogs.moderation",
            "cogs.music", "cogs.quotes", "cogs.replies", "cogs.stocks",
        }
        retained = {"успех", "успехстат", "топ", "roll", "огурчик", "увлажнение",
                    "logitech", "razer", "quote", "stock", "play", "addreply", "addword"}
        assert retained <= {command.name for command in bot.commands}
        assert retained <= {command.name for command in bot.tree.get_commands()}
        assert bot.get_command("stockquote") is bot.get_command("stock")
        assert bot.get_command("price") is bot.get_command("stock")
        assert bot.get_command("dc") is bot.get_command("leave")
        assert bot.tree.get_command("quote").get_command("show") is not None

        game = bot.get_command("успех")
        monkeypatch.setattr(game.cog.rng, "randint", AsyncMock(return_value=90))
        ctx = SimpleNamespace(
            guild=SimpleNamespace(id=10),
            author=SimpleNamespace(id=20, name="Test", mention="<@20>"),
            interaction=None,
            send=AsyncMock(),
        )
        await game.callback(game.cog, ctx)
        await game.callback(game.cog, ctx)

        assert "<@20>" in ctx.send.await_args_list[0].args[0]
        assert ctx.send.await_args_list[1].kwargs["embed"].title == "Command on Cooldown"
        assert await game.cog.db.get_total_success(10, 20) == 6
