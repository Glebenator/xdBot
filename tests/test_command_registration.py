import asyncio

import discord
from discord.ext import commands

import cogs.quotes as quotes_cog
import cogs.stocks as stocks_cog


def test_quote_and_stock_commands_register_without_alias_collision(monkeypatch) -> None:
    async def run_test() -> None:
        monkeypatch.setattr(quotes_cog, "get_database_handler", lambda: object())
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

        await bot.add_cog(quotes_cog.Quotes(bot))
        await bot.add_cog(stocks_cog.Stocks(bot))

        quote = bot.get_command("quote")
        stock = bot.get_command("stock")
        stockquote = bot.get_command("stockquote")
        price = bot.get_command("price")

        assert quote is not None
        assert quote.cog_name == "Quotes"
        assert stock is not None
        assert stock.cog_name == "Stocks"
        assert stockquote is stock
        assert price is stock

        await bot.close()

    asyncio.run(run_test())
