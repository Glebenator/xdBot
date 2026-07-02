# utils/stock_tool.py
"""Polygon.io stock market tool integration for LLM function calling."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from utils.polygon_handler import PolygonHandler

logger = logging.getLogger(__name__)


class StockMarketTool:
    """Stock market data tool for LLM integration using Polygon.io API."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        """Initialize the stock market tool.

        Args:
            api_key: Polygon.io API key
        """
        self.api_key = api_key
        self.polygon = PolygonHandler(api_key)

    async def close(self) -> None:
        """Close the Polygon handler session."""
        await self.polygon.close()

    def _error_response(self, message: str, **extra: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"error": message}
        payload.update(extra)
        return payload

    def get_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for this tool.

        Returns:
            Dictionary containing the tool schema for LLM function calling
        """
        return {
            "type": "function",
            "function": {
                "name": "get_stock_price",
                "description": "Get real-time stock price and market data for a publicly traded company. USE THIS TOOL for any questions about stock prices, stock performance, how a stock is doing, market data, or trading information. Examples: 'What's Apple stock price?', 'How is Tesla doing?', 'AAPL stock today', 'stock price of Microsoft'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'AAPL' for Apple, 'TSLA' for Tesla, 'MSFT' for Microsoft). If you don't know the ticker, use search_stocks first."
                        }
                    },
                    "required": ["ticker"]
                }
            }
        }

    def get_search_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for stock search.

        Returns:
            Dictionary containing the search tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": "search_stocks",
                "description": "Search for stock ticker symbols by company name. USE THIS TOOL when you need to find the ticker symbol for a company before using get_stock_price. Examples: 'Find ticker for Apple', 'What's the symbol for Tesla?', 'Search for NVIDIA stock'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Company name or partial ticker symbol to search for (e.g., 'Apple', 'Tesla', 'NVID')"
                        }
                    },
                    "required": ["query"]
                }
            }
        }

    def get_market_status_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for market status.

        Returns:
            Dictionary containing the market status tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": "get_market_status",
                "description": "Check if the stock market is currently open or closed. USE THIS TOOL for questions about market hours, trading status, or whether markets are open. Returns status for major US exchanges (NYSE, NASDAQ, OTC).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }

    def get_rsi_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for RSI indicator.

        Returns:
            Dictionary containing the RSI tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": "get_stock_rsi",
                "description": "Get Relative Strength Index (RSI) for a stock to identify overbought/oversold conditions. RSI ranges 0-100: >70 = overbought (potential sell), <30 = oversold (potential buy), ~50 = neutral. USE THIS TOOL for questions about momentum, whether a stock is overbought or oversold, or timing entries/exits. Examples: 'Is Apple overbought?', 'What's the RSI for Tesla?', 'Check momentum of NVDA'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'AAPL', 'TSLA', 'MSFT')"
                        },
                        "window": {
                            "type": "integer",
                            "description": "RSI period in days (default 14). Common values: 9 (fast), 14 (standard), 21 (slow)",
                            "default": 14
                        }
                    },
                    "required": ["ticker"]
                }
            }
        }

    def get_sma_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for SMA indicator.

        Returns:
            Dictionary containing the SMA tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": "get_stock_sma",
                "description": "Get Simple Moving Average (SMA) for a stock to identify trends. Price above SMA = uptrend (bullish), price below SMA = downtrend (bearish). USE THIS TOOL for questions about trends, moving averages, support/resistance levels. Examples: 'What's the 50-day moving average for Apple?', 'Is Tesla above its 200-day SMA?', 'Show me the trend for MSFT'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'AAPL', 'TSLA', 'MSFT')"
                        },
                        "window": {
                            "type": "integer",
                            "description": "SMA period in days (default 50). Common values: 20 (short), 50 (medium), 200 (long)",
                            "default": 50
                        }
                    },
                    "required": ["ticker"]
                }
            }
        }

    def get_ema_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for EMA indicator.

        Returns:
            Dictionary containing the EMA tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": "get_stock_ema",
                "description": "Get Exponential Moving Average (EMA) for a stock - reacts faster to price changes than SMA. Price above EMA = uptrend (bullish), price below EMA = downtrend (bearish). USE THIS TOOL for short-term trend detection, MACD components. Examples: 'What's the 12-day EMA for Tesla?', 'Check the fast EMA for AAPL', 'Is NVDA above its 26-day EMA?'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'AAPL', 'TSLA', 'MSFT')"
                        },
                        "window": {
                            "type": "integer",
                            "description": "EMA period in days (default 50). Common values: 12, 26 (MACD), 50, 200",
                            "default": 50
                        }
                    },
                    "required": ["ticker"]
                }
            }
        }

    def get_macd_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for MACD indicator.

        Returns:
            Dictionary containing the MACD tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": "get_stock_macd",
                "description": "Get MACD (Moving Average Convergence Divergence) for momentum and buy/sell signals. MACD > Signal = bullish, MACD < Signal = bearish. Detects crossovers as strong buy/sell signals. USE THIS TOOL for momentum questions, buy/sell timing, trend changes. Examples: 'What's the MACD for Apple?', 'Is Tesla showing bullish momentum?', 'Check MACD crossover for NVDA'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'AAPL', 'TSLA', 'MSFT')"
                        }
                    },
                    "required": ["ticker"]
                }
            }
        }

    def get_golden_cross_tool_schema(self) -> Dict[str, Any]:
        """Get the OpenAI function calling schema for golden cross detection.

        Returns:
            Dictionary containing the golden cross tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": "detect_golden_cross",
                "description": "Detect golden cross or death cross pattern - one of the most powerful trend reversal signals. Golden Cross (VERY BULLISH): 50-day SMA crosses above 200-day SMA. Death Cross (VERY BEARISH): 50-day SMA crosses below 200-day SMA. USE THIS TOOL for major trend analysis, long-term signals, reversal detection. Examples: 'Has Apple had a golden cross?', 'Check for death cross in SPY', 'Any crossover signals for Tesla?'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., 'AAPL', 'SPY', 'TSLA')"
                        }
                    },
                    "required": ["ticker"]
                }
            }
        }

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get all available tool schemas for stock market operations.

        Returns:
            List of tool schemas
        """
        return [
            self.get_tool_schema(),
            self.get_search_tool_schema(),
            self.get_market_status_tool_schema(),
            self.get_rsi_tool_schema(),
            self.get_sma_tool_schema(),
            self.get_ema_tool_schema(),
            self.get_macd_tool_schema(),
            self.get_golden_cross_tool_schema()
        ]

    async def get_stock_price(self, ticker: str) -> Dict[str, Any]:
        """Get stock price and market data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary containing formatted stock data
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured",
                "ticker": ticker.upper()
            }

        try:
            # Try previous close first (works on free tier)
            try:
                prev_data = await self.polygon.get_previous_close(ticker)
                results = prev_data.get("results", [])

                if results:
                    result = results[0]
                    logger.info(f"Successfully fetched previous close data for {ticker}")
                    return {
                        "ticker": ticker.upper(),
                        "price": result.get("c", 0),
                        "open": result.get("o", 0),
                        "high": result.get("h", 0),
                        "low": result.get("l", 0),
                        "volume": result.get("v", 0),
                        "change": result.get("c", 0) - result.get("o", 0),
                        "change_percent": ((result.get("c", 0) - result.get("o", 0)) / result.get("o", 1)) * 100,
                        "data_type": "previous_close",
                        "note": "Previous trading day data (snapshot requires paid plan)"
                    }
            except (aiohttp.ClientError, ValueError, TimeoutError) as prev_error:
                # If previous close fails, try snapshot (for paid plans)
                logger.debug(f"Previous close failed for {ticker}, trying snapshot: {prev_error}")

                try:
                    data = await self.polygon.get_snapshot(ticker)
                    ticker_data = data.get("ticker", {})
                    day_data = ticker_data.get("day", {})
                    prev_day_data = ticker_data.get("prevDay", {})

                    if day_data:
                        current_price = day_data.get("c", 0)
                        prev_close = prev_day_data.get("c", current_price)
                        change = current_price - prev_close
                        change_percent = (change / prev_close * 100) if prev_close > 0 else 0

                        logger.info(f"Successfully fetched snapshot data for {ticker}")
                        return {
                            "ticker": ticker.upper(),
                            "price": current_price,
                            "open": day_data.get("o", 0),
                            "high": day_data.get("h", 0),
                            "low": day_data.get("l", 0),
                            "volume": day_data.get("v", 0),
                            "previous_close": prev_close,
                            "change": change,
                            "change_percent": change_percent,
                            "data_type": "snapshot"
                        }
                except (aiohttp.ClientError, ValueError, TimeoutError) as snap_error:
                    logger.debug(f"Snapshot also failed for {ticker}: {snap_error}")
                    # Both failed, raise the original error
                    raise prev_error

            # If we get here, no data was found
            return {
                "error": f"No data found for ticker {ticker.upper()}",
                "ticker": ticker.upper()
            }

        except (aiohttp.ClientError, ValueError, TimeoutError) as e:
            logger.warning("Error fetching stock price for %s: %s", ticker, e)

            # Provide helpful error message based on error type
            error_str = str(e)
            if "403" in error_str or "Forbidden" in error_str:
                return self._error_response(
                    f"Unable to fetch data for {ticker.upper()}. This may be due to API plan limitations. Free tier has limited endpoints.",
                    ticker=ticker.upper(),
                    suggestion="Verify your API key has access to stock data endpoints at polygon.io/dashboard",
                )
            return self._error_response(
                f"Failed to fetch data for {ticker.upper()}: {str(e)}",
                ticker=ticker.upper(),
            )
        except Exception as e:
            logger.exception("Unexpected stock price error for %s", ticker)
            return self._error_response(
                f"Failed to fetch data for {ticker.upper()}: {str(e)}",
                ticker=ticker.upper(),
            )

    async def search_stocks(self, query: str) -> Dict[str, Any]:
        """Search for stock tickers.

        Args:
            query: Search query (company name or partial ticker)

        Returns:
            Dictionary containing search results
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured",
                "query": query
            }

        try:
            data = await self.polygon.search_tickers(query, limit=5)
            results = data.get("results", [])

            if not results:
                return {
                    "query": query,
                    "results": [],
                    "message": f"No tickers found for '{query}'"
                }

            formatted_results = []
            for result in results:
                formatted_results.append({
                    "ticker": result.get("ticker", "N/A"),
                    "name": result.get("name", "N/A"),
                    "market": result.get("market", "N/A"),
                    "type": result.get("type", "N/A")
                })

            return {
                "query": query,
                "results": formatted_results,
                "count": len(formatted_results)
            }

        except (aiohttp.ClientError, ValueError, TimeoutError) as e:
            logger.warning("Error searching stocks for '%s': %s", query, e)
            return self._error_response(f"Failed to search for '{query}': {str(e)}", query=query)
        except Exception as e:
            logger.exception("Unexpected stock search error for '%s'", query)
            return self._error_response(f"Failed to search for '{query}': {str(e)}", query=query)

    async def get_market_status(self) -> Dict[str, Any]:
        """Get current market status.

        Returns:
            Dictionary containing market status information
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured"
            }

        try:
            data = await self.polygon.get_market_status()

            market = data.get("market", "unknown")
            server_time = data.get("serverTime", "N/A")
            exchanges = data.get("exchanges", {})

            return {
                "overall_status": market,
                "server_time": server_time,
                "nyse": exchanges.get("nyse", "unknown"),
                "nasdaq": exchanges.get("nasdaq", "unknown"),
                "otc": exchanges.get("otc", "unknown"),
                "is_open": market == "open"
            }

        except (aiohttp.ClientError, ValueError, TimeoutError) as e:
            logger.warning("Error fetching market status: %s", e)
            return self._error_response(f"Failed to fetch market status: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected market status error")
            return self._error_response(f"Failed to fetch market status: {str(e)}")

    async def get_stock_rsi(self, ticker: str, window: int = 14) -> Dict[str, Any]:
        """Get RSI indicator for a stock.

        Args:
            ticker: Stock ticker symbol
            window: RSI period (default 14)

        Returns:
            Dictionary containing RSI data and interpretation
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured",
                "ticker": ticker.upper()
            }

        try:
            data = await self.polygon.get_rsi(ticker, timespan="day", window=window, limit=5)
            results = data.get("results", {}).get("values", [])

            if not results:
                return {
                    "error": f"No RSI data available for {ticker.upper()}",
                    "ticker": ticker.upper()
                }

            latest = results[-1]
            rsi_value = latest.get("value", 0)
            timestamp = latest.get("timestamp", 0)
            date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")

            # Determine signal
            if rsi_value >= 70:
                signal = "overbought"
                interpretation = "Stock may be overvalued - potential sell signal"
            elif rsi_value <= 30:
                signal = "oversold"
                interpretation = "Stock may be undervalued - potential buy signal"
            else:
                signal = "neutral"
                interpretation = "No strong signal - hold or wait"

            return {
                "ticker": ticker.upper(),
                "rsi": round(rsi_value, 2),
                "window": window,
                "date": date,
                "signal": signal,
                "interpretation": interpretation
            }

        except (aiohttp.ClientError, ValueError, TimeoutError) as e:
            logger.warning("Error fetching RSI for %s: %s", ticker, e)
            return self._error_response(
                f"Failed to fetch RSI for {ticker.upper()}: {str(e)}",
                ticker=ticker.upper(),
            )
        except Exception as e:
            logger.exception("Unexpected RSI error for %s", ticker)
            return self._error_response(
                f"Failed to fetch RSI for {ticker.upper()}: {str(e)}",
                ticker=ticker.upper(),
            )

    async def get_stock_sma(self, ticker: str, window: int = 50) -> Dict[str, Any]:
        """Get SMA indicator for a stock.

        Args:
            ticker: Stock ticker symbol
            window: SMA period (default 50)

        Returns:
            Dictionary containing SMA data and interpretation
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured",
                "ticker": ticker.upper()
            }

        try:
            # Get SMA data
            sma_data = await self.polygon.get_sma(ticker, timespan="day", window=window, limit=5)
            sma_results = sma_data.get("results", {}).get("values", [])

            # Get current price
            price_data = await self.polygon.get_previous_close(ticker)
            current_price = price_data.get("results", [{}])[0].get("c", 0)

            if not sma_results:
                return {
                    "error": f"No SMA data available for {ticker.upper()}",
                    "ticker": ticker.upper()
                }

            latest = sma_results[-1]
            sma_value = latest.get("value", 0)
            timestamp = latest.get("timestamp", 0)
            date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")

            # Determine trend
            if current_price > sma_value:
                signal = "uptrend"
                interpretation = f"Price (${current_price:.2f}) is above SMA - bullish signal"
            else:
                signal = "downtrend"
                interpretation = f"Price (${current_price:.2f}) is below SMA - bearish signal"

            distance = ((current_price - sma_value) / sma_value * 100) if sma_value > 0 else 0

            return {
                "ticker": ticker.upper(),
                "current_price": round(current_price, 2),
                "sma": round(sma_value, 2),
                "window": window,
                "date": date,
                "signal": signal,
                "distance_percent": round(distance, 2),
                "interpretation": interpretation
            }

        except Exception as e:
            logger.error(f"Error fetching SMA for {ticker}: {e}")
            return {
                "error": f"Failed to fetch SMA for {ticker.upper()}: {str(e)}",
                "ticker": ticker.upper()
            }

    async def get_stock_ema(self, ticker: str, window: int = 50) -> Dict[str, Any]:
        """Get EMA indicator for a stock.

        Args:
            ticker: Stock ticker symbol
            window: EMA period (default 50)

        Returns:
            Dictionary containing EMA data and interpretation
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured",
                "ticker": ticker.upper()
            }

        try:
            # Get EMA data
            ema_data = await self.polygon.get_ema(ticker, timespan="day", window=window, limit=5)
            ema_results = ema_data.get("results", {}).get("values", [])

            # Get current price
            price_data = await self.polygon.get_previous_close(ticker)
            current_price = price_data.get("results", [{}])[0].get("c", 0)

            if not ema_results:
                return {
                    "error": f"No EMA data available for {ticker.upper()}",
                    "ticker": ticker.upper()
                }

            latest = ema_results[-1]
            ema_value = latest.get("value", 0)
            timestamp = latest.get("timestamp", 0)
            date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")

            # Determine trend
            if current_price > ema_value:
                signal = "uptrend"
                interpretation = f"Price (${current_price:.2f}) is above EMA - bullish signal"
            else:
                signal = "downtrend"
                interpretation = f"Price (${current_price:.2f}) is below EMA - bearish signal"

            distance = ((current_price - ema_value) / ema_value * 100) if ema_value > 0 else 0

            return {
                "ticker": ticker.upper(),
                "current_price": round(current_price, 2),
                "ema": round(ema_value, 2),
                "window": window,
                "date": date,
                "signal": signal,
                "distance_percent": round(distance, 2),
                "interpretation": interpretation
            }

        except Exception as e:
            logger.error(f"Error fetching EMA for {ticker}: {e}")
            return {
                "error": f"Failed to fetch EMA for {ticker.upper()}: {str(e)}",
                "ticker": ticker.upper()
            }

    async def get_stock_macd(self, ticker: str) -> Dict[str, Any]:
        """Get MACD indicator for a stock.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary containing MACD data and interpretation
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured",
                "ticker": ticker.upper()
            }

        try:
            data = await self.polygon.get_macd(ticker, timespan="day", limit=10)
            results = data.get("results", {}).get("values", [])

            if not results:
                return {
                    "error": f"No MACD data available for {ticker.upper()}",
                    "ticker": ticker.upper()
                }

            latest = results[-1]
            macd_value = latest.get("value", 0)
            signal = latest.get("signal", 0)
            histogram = latest.get("histogram", 0)
            timestamp = latest.get("timestamp", 0)
            date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")

            # Determine signal
            if macd_value > signal:
                trend = "bullish"
                interpretation = "MACD above signal line - positive momentum"
            else:
                trend = "bearish"
                interpretation = "MACD below signal line - negative momentum"

            # Check for crossover
            crossover = None
            if len(results) > 1:
                prev = results[-2]
                prev_macd = prev.get("value", 0)
                prev_signal = prev.get("signal", 0)

                if prev_macd <= prev_signal and macd_value > signal:
                    crossover = "bullish_crossover"
                    interpretation += " - STRONG BUY SIGNAL (bullish crossover detected)"
                elif prev_macd >= prev_signal and macd_value < signal:
                    crossover = "bearish_crossover"
                    interpretation += " - STRONG SELL SIGNAL (bearish crossover detected)"

            return {
                "ticker": ticker.upper(),
                "macd": round(macd_value, 4),
                "signal_line": round(signal, 4),
                "histogram": round(histogram, 4),
                "date": date,
                "trend": trend,
                "crossover": crossover,
                "interpretation": interpretation
            }

        except Exception as e:
            logger.error(f"Error fetching MACD for {ticker}: {e}")
            return {
                "error": f"Failed to fetch MACD for {ticker.upper()}: {str(e)}",
                "ticker": ticker.upper()
            }

    async def detect_golden_cross(self, ticker: str) -> Dict[str, Any]:
        """Detect golden cross or death cross pattern.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary containing crossover detection and analysis
        """
        if not self.api_key:
            return {
                "error": "Stock market data is not configured",
                "ticker": ticker.upper()
            }

        try:
            # Fetch both SMAs with history
            sma_50_data = await self.polygon.get_sma(ticker, window=50, limit=10)
            sma_200_data = await self.polygon.get_sma(ticker, window=200, limit=10)

            sma_50_results = sma_50_data.get("results", {}).get("values", [])
            sma_200_results = sma_200_data.get("results", {}).get("values", [])

            if not sma_50_results or not sma_200_results:
                return {
                    "error": f"Insufficient SMA data for {ticker.upper()}. Stock may be too new.",
                    "ticker": ticker.upper()
                }

            if len(sma_50_results) < 2 or len(sma_200_results) < 2:
                return {
                    "error": f"Need more historical data to detect crossovers for {ticker.upper()}",
                    "ticker": ticker.upper()
                }

            # Get current and previous values
            current_50 = sma_50_results[-1].get("value", 0)
            current_200 = sma_200_results[-1].get("value", 0)
            previous_50 = sma_50_results[-2].get("value", 0)
            previous_200 = sma_200_results[-2].get("value", 0)

            # Detect crossover
            crossover = None
            signal = None
            interpretation = ""

            # Golden cross: 50 SMA crosses above 200 SMA
            if previous_50 <= previous_200 and current_50 > current_200:
                crossover = "GOLDEN_CROSS"
                signal = "STRONG BUY"
                interpretation = "🚀 GOLDEN CROSS DETECTED! The 50-day SMA has crossed above the 200-day SMA. This is an extremely bullish long-term signal indicating a major uptrend."
            # Death cross: 50 SMA crosses below 200 SMA
            elif previous_50 >= previous_200 and current_50 < current_200:
                crossover = "DEATH_CROSS"
                signal = "STRONG SELL"
                interpretation = "💀 DEATH CROSS DETECTED! The 50-day SMA has crossed below the 200-day SMA. This is an extremely bearish long-term signal indicating a major downtrend."
            # No crossover - just report current state
            elif current_50 > current_200:
                crossover = None
                signal = "BULLISH"
                distance_pct = ((current_50 - current_200) / current_200) * 100
                interpretation = f"📈 Bullish alignment: 50-day SMA is {distance_pct:.2f}% above 200-day SMA. Uptrend confirmed, but no recent crossover."
            else:
                crossover = None
                signal = "BEARISH"
                distance_pct = ((current_200 - current_50) / current_200) * 100
                interpretation = f"📉 Bearish alignment: 50-day SMA is {distance_pct:.2f}% below 200-day SMA. Downtrend confirmed, but no recent crossover."

            return {
                "ticker": ticker.upper(),
                "sma_50": round(current_50, 2),
                "sma_200": round(current_200, 2),
                "crossover": crossover,
                "signal": signal,
                "interpretation": interpretation,
                "alignment": "bullish" if current_50 > current_200 else "bearish"
            }

        except Exception as e:
            logger.error(f"Error detecting golden cross for {ticker}: {e}")
            return {
                "error": f"Failed to detect golden cross for {ticker.upper()}: {str(e)}",
                "ticker": ticker.upper()
            }

    async def execute_tool_call(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool call based on function name and arguments.

        Args:
            function_name: Name of the function to call
            arguments: Arguments for the function

        Returns:
            Result of the function call
        """
        if function_name == "get_stock_price":
            ticker = arguments.get("ticker", "")
            return await self.get_stock_price(ticker)
        elif function_name == "search_stocks":
            query = arguments.get("query", "")
            return await self.search_stocks(query)
        elif function_name == "get_market_status":
            return await self.get_market_status()
        elif function_name == "get_stock_rsi":
            ticker = arguments.get("ticker", "")
            window = arguments.get("window", 14)
            return await self.get_stock_rsi(ticker, window)
        elif function_name == "get_stock_sma":
            ticker = arguments.get("ticker", "")
            window = arguments.get("window", 50)
            return await self.get_stock_sma(ticker, window)
        elif function_name == "get_stock_ema":
            ticker = arguments.get("ticker", "")
            window = arguments.get("window", 50)
            return await self.get_stock_ema(ticker, window)
        elif function_name == "get_stock_macd":
            ticker = arguments.get("ticker", "")
            return await self.get_stock_macd(ticker)
        elif function_name == "detect_golden_cross":
            ticker = arguments.get("ticker", "")
            return await self.detect_golden_cross(ticker)
        else:
            return {"error": f"Unknown function: {function_name}"}


    def format_price_response(self, data: Dict[str, Any]) -> str:
        """Format stock price data for display in chat.

        Args:
            data: Stock price data dictionary

        Returns:
            Formatted string response
        """
        if "error" in data:
            return f"❌ {data['error']}"

        ticker = data.get("ticker", "N/A")
        price = data.get("price", 0)
        change = data.get("change", 0)
        change_percent = data.get("change_percent", 0)
        volume = data.get("volume", 0)

        emoji = "📈" if change >= 0 else "📉"
        sign = "+" if change >= 0 else ""

        return f"{emoji} **{ticker}**: ${price:.2f} ({sign}${change:.2f}, {sign}{change_percent:.2f}%) | Volume: {volume:,}"

    def format_search_response(self, data: Dict[str, Any]) -> str:
        """Format stock search results for display in chat.

        Args:
            data: Search results dictionary

        Returns:
            Formatted string response
        """
        if "error" in data:
            return f"❌ {data['error']}"

        results = data.get("results", [])
        if not results:
            return f"🔍 No results found for '{data.get('query', '')}'"

        lines = [f"🔍 Found {len(results)} ticker(s):"]
        for r in results:
            lines.append(f"• **{r['ticker']}** - {r['name']} ({r['market']})")

        return "\n".join(lines)

    def format_market_status_response(self, data: Dict[str, Any]) -> str:
        """Format market status for display in chat.

        Args:
            data: Market status dictionary

        Returns:
            Formatted string response
        """
        if "error" in data:
            return f"❌ {data['error']}"

        status = data.get("overall_status", "unknown")
        emoji = "🟢" if status == "open" else "🔴" if status == "closed" else "🟡"

        return f"{emoji} Market is **{status.upper()}** | NYSE: {data.get('nyse', 'N/A')} | NASDAQ: {data.get('nasdaq', 'N/A')}"

    def format_rsi_response(self, data: Dict[str, Any]) -> str:
        """Format RSI data for display in chat.

        Args:
            data: RSI data dictionary

        Returns:
            Formatted string response
        """
        if "error" in data:
            return f"❌ {data['error']}"

        ticker = data.get("ticker", "N/A")
        rsi = data.get("rsi", 0)
        signal = data.get("signal", "unknown")
        interpretation = data.get("interpretation", "")

        # Signal emoji
        if signal == "overbought":
            emoji = "🔴"
        elif signal == "oversold":
            emoji = "🟢"
        else:
            emoji = "🟡"

        return f"📊 **{ticker}** RSI ({data.get('window', 14)}-day): **{rsi:.2f}** {emoji}\n{signal.capitalize()}: {interpretation}"

    def format_sma_response(self, data: Dict[str, Any]) -> str:
        """Format SMA data for display in chat.

        Args:
            data: SMA data dictionary

        Returns:
            Formatted string response
        """
        if "error" in data:
            return f"❌ {data['error']}"

        ticker = data.get("ticker", "N/A")
        current_price = data.get("current_price", 0)
        sma = data.get("sma", 0)
        signal = data.get("signal", "unknown")
        distance = data.get("distance_percent", 0)

        emoji = "📈" if signal == "uptrend" else "📉"
        sign = "+" if distance >= 0 else ""

        return f"📊 **{ticker}** SMA ({data.get('window', 50)}-day): ${sma:.2f}\nCurrent Price: ${current_price:.2f} ({sign}{distance:.2f}%) {emoji}\n{signal.capitalize()}: {data.get('interpretation', '')}"

    def format_ema_response(self, data: Dict[str, Any]) -> str:
        """Format EMA data for display in chat.

        Args:
            data: EMA data dictionary

        Returns:
            Formatted string response
        """
        if "error" in data:
            return f"❌ {data['error']}"

        ticker = data.get("ticker", "N/A")
        current_price = data.get("current_price", 0)
        ema = data.get("ema", 0)
        signal = data.get("signal", "unknown")
        distance = data.get("distance_percent", 0)

        emoji = "📈" if signal == "uptrend" else "📉"
        sign = "+" if distance >= 0 else ""

        return f"📊 **{ticker}** EMA ({data.get('window', 50)}-day): ${ema:.2f}\nCurrent Price: ${current_price:.2f} ({sign}{distance:.2f}%) {emoji}\n{signal.capitalize()}: {data.get('interpretation', '')}"

    def format_macd_response(self, data: Dict[str, Any]) -> str:
        """Format MACD data for display in chat.

        Args:
            data: MACD data dictionary

        Returns:
            Formatted string response
        """
        if "error" in data:
            return f"❌ {data['error']}"

        ticker = data.get("ticker", "N/A")
        macd = data.get("macd", 0)
        signal_line = data.get("signal_line", 0)
        histogram = data.get("histogram", 0)
        trend = data.get("trend", "unknown")
        crossover = data.get("crossover")

        emoji = "🟢" if trend == "bullish" else "🔴"

        result = f"📊 **{ticker}** MACD: **{macd:.4f}** | Signal: **{signal_line:.4f}** | Histogram: {histogram:.4f} {emoji}\n"
        result += f"{trend.capitalize()}: {data.get('interpretation', '')}"

        if crossover == "bullish_crossover":
            result = "🚀 " + result
        elif crossover == "bearish_crossover":
            result = "⚠️ " + result

        return result
