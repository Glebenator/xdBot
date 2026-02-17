"""Polygon.io API handler for stock market data.

This module provides a wrapper around the Polygon.io REST API for fetching
stock market data including quotes, tickers, aggregates, and company information.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class PolygonHandler:
    """Handler for Polygon.io API interactions."""

    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Polygon.io handler.

        Args:
            api_key: Polygon.io API key. If None, API calls will fail.
        """
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a request to the Polygon.io API.

        Args:
            endpoint: API endpoint (e.g., '/v2/aggs/ticker/AAPL/range/1/day/2023-01-09/2023-01-09')
            params: Optional query parameters

        Returns:
            JSON response as a dictionary

        Raises:
            ValueError: If API key is not configured
            aiohttp.ClientError: If the request fails
        """
        if not self.api_key:
            raise ValueError("Polygon.io API key is not configured")

        session = await self._get_session()

        # Add API key to params
        if params is None:
            params = {}
        params["apiKey"] = self.api_key

        url = f"{self.BASE_URL}{endpoint}"

        logger.debug(f"Making request to Polygon.io: {endpoint}")

        async with session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get("status") == "ERROR":
                error_msg = data.get("error", "Unknown error")
                logger.error(f"Polygon.io API error: {error_msg}")
                raise ValueError(f"API Error: {error_msg}")

            return data

    async def get_ticker_details(self, ticker: str) -> Dict[str, Any]:
        """Get detailed information about a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            Dictionary containing ticker details
        """
        endpoint = f"/v3/reference/tickers/{ticker.upper()}"
        return await self._make_request(endpoint)

    async def get_previous_close(self, ticker: str) -> Dict[str, Any]:
        """Get the previous day's close for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            Dictionary containing previous close data
        """
        endpoint = f"/v2/aggs/ticker/{ticker.upper()}/prev"
        return await self._make_request(endpoint, params={"adjusted": "true"})

    async def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        """Get the current snapshot for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            Dictionary containing current snapshot data
        """
        endpoint = f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
        return await self._make_request(endpoint)

    async def get_aggregates(
        self,
        ticker: str,
        multiplier: int = 1,
        timespan: str = "day",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 120
    ) -> Dict[str, Any]:
        """Get aggregate bars for a ticker over a date range.

        NOTE: Free tier supports this but with rate limits (5 calls/min)

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            multiplier: Size of the timespan multiplier (e.g., 1)
            timespan: Size of the time window ('minute', 'hour', 'day', 'week', 'month', 'quarter', 'year')
            from_date: Start date (YYYY-MM-DD format). Defaults to 30 days ago
            to_date: End date (YYYY-MM-DD format). Defaults to today
            limit: Maximum number of results (default 120)

        Returns:
            Dictionary containing aggregate data
        """
        if from_date is None:
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")

        endpoint = f"/v2/aggs/ticker/{ticker.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        return await self._make_request(endpoint, params={"adjusted": "true", "limit": limit})

    async def get_daily_open_close(
        self,
        ticker: str,
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get the open, close and afterhours prices for a specific date.

        FREE TIER: ✅ Available - Daily OHLCV data

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            date: Date in YYYY-MM-DD format. Defaults to previous trading day

        Returns:
            Dictionary containing daily open/close data
        """
        if date is None:
            # Default to yesterday
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        endpoint = f"/v1/open-close/{ticker.upper()}/{date}"
        return await self._make_request(endpoint, params={"adjusted": "true"})

    async def get_grouped_daily(
        self,
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get the daily OHLCV for the entire stock market.

        FREE TIER: ✅ Available - Market-wide daily data

        Args:
            date: Date in YYYY-MM-DD format. Defaults to previous trading day

        Returns:
            Dictionary containing grouped daily data for all tickers
        """
        if date is None:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        endpoint = f"/v2/aggs/grouped/locale/us/market/stocks/{date}"
        return await self._make_request(endpoint, params={"adjusted": "true"})

    async def get_ticker_news(
        self,
        ticker: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get news articles for a ticker or the market.

        FREE TIER: ✅ Available - News articles

        Args:
            ticker: Stock ticker symbol (optional - if None, gets market news)
            limit: Maximum number of articles (default 10)

        Returns:
            Dictionary containing news articles
        """
        endpoint = "/v2/reference/news"
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker.upper()

        return await self._make_request(endpoint, params=params)

    async def get_dividends(
        self,
        ticker: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get dividend data for a ticker.

        FREE TIER: ✅ Available - Corporate actions (dividends)

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            limit: Maximum number of results (default 10)

        Returns:
            Dictionary containing dividend data
        """
        endpoint = "/v3/reference/dividends"
        params = {
            "ticker": ticker.upper(),
            "limit": limit
        }
        return await self._make_request(endpoint, params=params)

    async def get_stock_splits(
        self,
        ticker: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get stock split data for a ticker.

        FREE TIER: ✅ Available - Corporate actions (splits)

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            limit: Maximum number of results (default 10)

        Returns:
            Dictionary containing stock split data
        """
        endpoint = "/v3/reference/splits"
        params = {
            "ticker": ticker.upper(),
            "limit": limit
        }
        return await self._make_request(endpoint, params=params)

    async def get_sma(
        self,
        ticker: str,
        timespan: str = "day",
        window: int = 50,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get Simple Moving Average (SMA) technical indicator.

        FREE TIER: ✅ Available - Technical indicators

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            timespan: Timespan ('minute', 'hour', 'day', 'week', 'month', 'quarter', 'year')
            window: Window size for SMA calculation (default 50)
            limit: Maximum number of results (default 10)

        Returns:
            Dictionary containing SMA data
        """
        endpoint = f"/v1/indicators/sma/{ticker.upper()}"
        params = {
            "timespan": timespan,
            "window": window,
            "limit": limit,
            "adjusted": "true"
        }
        return await self._make_request(endpoint, params=params)

    async def get_ema(
        self,
        ticker: str,
        timespan: str = "day",
        window: int = 50,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get Exponential Moving Average (EMA) technical indicator.

        FREE TIER: ✅ Available - Technical indicators

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            timespan: Timespan ('minute', 'hour', 'day', 'week', 'month', 'quarter', 'year')
            window: Window size for EMA calculation (default 50)
            limit: Maximum number of results (default 10)

        Returns:
            Dictionary containing EMA data
        """
        endpoint = f"/v1/indicators/ema/{ticker.upper()}"
        params = {
            "timespan": timespan,
            "window": window,
            "limit": limit,
            "adjusted": "true"
        }
        return await self._make_request(endpoint, params=params)

    async def get_macd(
        self,
        ticker: str,
        timespan: str = "day",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get MACD (Moving Average Convergence Divergence) technical indicator.

        FREE TIER: ✅ Available - Technical indicators

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            timespan: Timespan ('minute', 'hour', 'day', 'week', 'month', 'quarter', 'year')
            limit: Maximum number of results (default 10)

        Returns:
            Dictionary containing MACD data
        """
        endpoint = f"/v1/indicators/macd/{ticker.upper()}"
        params = {
            "timespan": timespan,
            "limit": limit,
            "adjusted": "true"
        }
        return await self._make_request(endpoint, params=params)

    async def get_rsi(
        self,
        ticker: str,
        timespan: str = "day",
        window: int = 14,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get RSI (Relative Strength Index) technical indicator.

        FREE TIER: ✅ Available - Technical indicators

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            timespan: Timespan ('minute', 'hour', 'day', 'week', 'month', 'quarter', 'year')
            window: Window size for RSI calculation (default 14)
            limit: Maximum number of results (default 10)

        Returns:
            Dictionary containing RSI data
        """
        endpoint = f"/v1/indicators/rsi/{ticker.upper()}"
        params = {
            "timespan": timespan,
            "window": window,
            "limit": limit,
            "adjusted": "true"
        }
        return await self._make_request(endpoint, params=params)

    async def search_tickers(
        self,
        search: str,
        market: str = "stocks",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Search for tickers by name or symbol.

        Args:
            search: Search query
            market: Market type ('stocks', 'crypto', 'fx', 'otc')
            limit: Maximum number of results

        Returns:
            Dictionary containing search results
        """
        endpoint = "/v3/reference/tickers"
        params = {
            "search": search,
            "market": market,
            "active": "true",
            "limit": limit
        }
        return await self._make_request(endpoint, params=params)

    async def get_market_status(self) -> Dict[str, Any]:
        """Get the current market status.

        Returns:
            Dictionary containing market status information
        """
        endpoint = "/v1/marketstatus/now"
        return await self._make_request(endpoint)

    def format_price(self, price: float) -> str:
        """Format a price value for display.

        Args:
            price: Price value

        Returns:
            Formatted price string
        """
        return f"${price:,.2f}"

    def format_percentage(self, percentage: float) -> str:
        """Format a percentage value for display.

        Args:
            percentage: Percentage value

        Returns:
            Formatted percentage string with emoji
        """
        emoji = "📈" if percentage >= 0 else "📉"
        sign = "+" if percentage >= 0 else ""
        return f"{emoji} {sign}{percentage:.2f}%"
