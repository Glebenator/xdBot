import asyncio
import json
import sqlite3

from utils.db_handler import DatabaseHandler
from utils.ollama_handler import LLMHandler, ProviderType
from utils.search_tool import TavilySearchTool
from utils.stock_tool import StockMarketTool


def test_tavily_tool_definition_compatibility() -> None:
    openai_def = TavilySearchTool.get_tool_definition()
    ollama_def = TavilySearchTool.get_ollama_tool_definition()

    assert openai_def["function"]["name"] == "tavily_search"
    assert ollama_def["function"]["name"] == "tavily_search"
    assert "query" in openai_def["function"]["parameters"]["required"]
    assert "query" in ollama_def["function"]["parameters"]["required"]


def test_llm_handler_advertises_stock_tools_only_with_polygon_key() -> None:
    with_stock = LLMHandler(polygon_api_key="polygon-key")
    without_stock = LLMHandler()

    with_stock_names = {
        schema["function"]["name"]
        for schema in with_stock._get_available_tool_schemas(ProviderType.OLLAMA)
    }
    without_stock_names = {
        schema["function"]["name"]
        for schema in without_stock._get_available_tool_schemas(ProviderType.OLLAMA)
    }

    assert "get_stock_price" in with_stock_names
    assert "detect_golden_cross" in with_stock_names
    assert "get_stock_price" not in without_stock_names


def test_mention_model_disables_tools(monkeypatch) -> None:
    import cogs.llm as llm_cog

    monkeypatch.setattr(llm_cog, "get_database_handler", lambda: object())

    cog = llm_cog.LLM(bot=object())

    assert cog.model_configs["mention"].supports_tools is False


def test_llm_handler_routes_stock_tool_calls_as_formatted_text() -> None:
    class FakeStockTool:
        async def execute_tool_call(self, function_name, arguments):
            assert function_name == "get_stock_price"
            assert arguments == {"ticker": "AAPL"}
            return {
                "ticker": "AAPL",
                "price": 200.0,
                "change": 1.5,
                "change_percent": 0.75,
                "volume": 1234,
            }

        def format_price_response(self, data):
            return f"{data['ticker']}: ${data['price']:.2f}"

        def format_search_response(self, data):
            return json.dumps(data)

        def format_market_status_response(self, data):
            return json.dumps(data)

        def format_rsi_response(self, data):
            return json.dumps(data)

        def format_sma_response(self, data):
            return json.dumps(data)

        def format_ema_response(self, data):
            return json.dumps(data)

        def format_macd_response(self, data):
            return json.dumps(data)

    async def run_test() -> None:
        handler = LLMHandler()
        handler._stock_tool = FakeStockTool()
        result = await handler._execute_tool_call({
            "id": "call-1",
            "function": {
                "name": "get_stock_price",
                "arguments": json.dumps({"ticker": "AAPL"}),
            },
        })

        assert result == "AAPL: $200.00"

    asyncio.run(run_test())


def test_stock_indicators_use_newest_first_values() -> None:
    class FakePolygon:
        async def get_rsi(self, ticker, timespan="day", window=14, limit=5):
            return {
                "results": {
                    "values": [
                        {"value": 72.4, "timestamp": 1_735_689_600_000},
                        {"value": 44.0, "timestamp": 1_735_603_200_000},
                    ]
                }
            }

        async def get_macd(self, ticker, timespan="day", limit=10):
            return {
                "results": {
                    "values": [
                        {
                            "value": 2.0,
                            "signal": 1.5,
                            "histogram": 0.5,
                            "timestamp": 1_735_689_600_000,
                        },
                        {
                            "value": 1.0,
                            "signal": 1.2,
                            "histogram": -0.2,
                            "timestamp": 1_735_603_200_000,
                        },
                    ]
                }
            }

        async def close(self):
            pass

    async def run_test() -> None:
        tool = StockMarketTool(api_key="polygon-key")
        tool.polygon = FakePolygon()

        rsi = await tool.get_stock_rsi("AAPL")
        macd = await tool.get_stock_macd("AAPL")

        assert rsi["rsi"] == 72.4
        assert rsi["signal"] == "overbought"
        assert macd["macd"] == 2.0
        assert macd["signal_line"] == 1.5
        assert macd["crossover"] == "bullish_crossover"

    asyncio.run(run_test())


def test_global_set_prompt_updates_existing_null_guild_row(tmp_path) -> None:
    async def run_test() -> None:
        db_path = tmp_path / "bot.db"
        handler = DatabaseHandler(str(db_path))

        await handler.set_prompt("chat", "first")
        await handler.set_prompt("chat", "second")

        assert await handler.get_prompt("chat") == "second"

        with sqlite3.connect(db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM prompts WHERE guild_id IS NULL AND model_name = ?",
                ("chat",),
            ).fetchone()[0]

        assert count == 1

    asyncio.run(run_test())
