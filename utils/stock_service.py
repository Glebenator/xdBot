# utils/stock_service.py
"""Stock data service - orchestrates API calls and data processing.

This service layer sits between the raw Polygon API handler and the commands,
providing a clean interface that returns typed models instead of raw dictionaries.
It handles data parsing, error handling, and business logic.
"""

from __future__ import annotations

from utils.polygon_handler import PolygonHandler
from utils.stock_models import (
    StockPrice, IndicatorValue, StockInfo, MACDIndicator,
    NewsArticle, Dividend, StockSplit
)
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class StockService:
    """High-level service for stock data operations.
    
    This service provides a clean, typed interface for fetching stock data.
    All methods return domain models instead of raw API dictionaries.
    """
    
    def __init__(self, polygon_handler: PolygonHandler):
        """Initialize the stock service.
        
        Args:
            polygon_handler: Configured PolygonHandler instance
        """
        self.polygon = polygon_handler
    
    async def get_current_price(self, ticker: str) -> StockPrice:
        """Get current stock price as a StockPrice model.
        
        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            
        Returns:
            StockPrice object with latest price data
            
        Raises:
            ValueError: If no price data is available
        """
        data = await self.polygon.get_previous_close(ticker)
        results = data.get("results", [])
        
        if not results:
            raise ValueError(f"No price data available for {ticker.upper()}")
        
        return StockPrice.from_polygon_result(ticker, results[0])
    
    async def get_price_history(
        self,
        ticker: str,
        days: int = 30,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[StockPrice]:
        """Get historical price data.
        
        Args:
            ticker: Stock ticker symbol
            days: Number of days of history (default 30, ignored if dates provided)
            from_date: Start date in YYYY-MM-DD format (optional)
            to_date: End date in YYYY-MM-DD format (optional)
            
        Returns:
            List of StockPrice objects, sorted by date (newest first)
        """
        if from_date is None:
            from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")
        
        data = await self.polygon.get_aggregates(
            ticker,
            from_date=from_date,
            to_date=to_date,
            limit=max(days * 2, 120)  # Request more than needed to handle weekends
        )
        
        results = data.get("results", [])
        prices = [StockPrice.from_polygon_result(ticker, r) for r in results]
        
        # Sort by date, newest first
        prices.sort(key=lambda p: p.timestamp, reverse=True)
        
        return prices
    
    async def get_rsi(
        self,
        ticker: str,
        window: int = 14,
        limit: int = 10
    ) -> List[IndicatorValue]:
        """Get RSI (Relative Strength Index) indicator values.
        
        Args:
            ticker: Stock ticker symbol
            window: RSI period (default 14 days)
            limit: Number of data points to return
            
        Returns:
            List of IndicatorValue objects for RSI
        """
        data = await self.polygon.get_rsi(ticker, window=window, limit=limit)
        results = data.get("results", {}).get("values", [])
        
        indicators = [
            IndicatorValue.from_polygon_result(ticker, r, "RSI", window)
            for r in results
        ]
        
        # Sort by date, newest first
        indicators.sort(key=lambda i: i.timestamp, reverse=True)
        
        return indicators
    
    async def get_sma(
        self,
        ticker: str,
        window: int = 50,
        limit: int = 10
    ) -> List[IndicatorValue]:
        """Get SMA (Simple Moving Average) indicator values.
        
        Args:
            ticker: Stock ticker symbol
            window: SMA period (default 50 days)
            limit: Number of data points to return
            
        Returns:
            List of IndicatorValue objects for SMA
        """
        data = await self.polygon.get_sma(ticker, window=window, limit=limit)
        results = data.get("results", {}).get("values", [])
        
        indicators = [
            IndicatorValue.from_polygon_result(ticker, r, "SMA", window)
            for r in results
        ]
        
        indicators.sort(key=lambda i: i.timestamp, reverse=True)
        return indicators
    
    async def get_ema(
        self,
        ticker: str,
        window: int = 50,
        limit: int = 10
    ) -> List[IndicatorValue]:
        """Get EMA (Exponential Moving Average) indicator values.
        
        Args:
            ticker: Stock ticker symbol
            window: EMA period (default 50 days)
            limit: Number of data points to return
            
        Returns:
            List of IndicatorValue objects for EMA
        """
        data = await self.polygon.get_ema(ticker, window=window, limit=limit)
        results = data.get("results", {}).get("values", [])
        
        indicators = [
            IndicatorValue.from_polygon_result(ticker, r, "EMA", window)
            for r in results
        ]
        
        indicators.sort(key=lambda i: i.timestamp, reverse=True)
        return indicators
    
    async def get_macd(
        self,
        ticker: str,
        limit: int = 10
    ) -> List[MACDIndicator]:
        """Get MACD (Moving Average Convergence Divergence) indicator values.
        
        Args:
            ticker: Stock ticker symbol
            limit: Number of data points to return
            
        Returns:
            List of MACDIndicator objects
        """
        data = await self.polygon.get_macd(ticker, limit=limit)
        results = data.get("results", {}).get("values", [])
        
        indicators = [
            MACDIndicator.from_polygon_result(ticker, r)
            for r in results
        ]
        
        indicators.sort(key=lambda i: i.timestamp, reverse=True)
        return indicators
    
    async def get_indicator(
        self,
        ticker: str,
        indicator_type: str,
        window: Optional[int] = None,
        limit: int = 10
    ) -> List[IndicatorValue]:
        """Generic method to fetch any indicator by type.
        
        This is a convenience method that routes to the appropriate
        specific indicator method based on indicator_type.
        
        Args:
            ticker: Stock ticker symbol
            indicator_type: Type of indicator ('RSI', 'SMA', 'EMA')
            window: Window period for the indicator
            limit: Number of data points to return
            
        Returns:
            List of IndicatorValue objects
            
        Raises:
            ValueError: If indicator_type is not supported
        """
        indicator_type = indicator_type.upper()
        
        if indicator_type == "RSI":
            window = window or 14
            return await self.get_rsi(ticker, window, limit)
        elif indicator_type == "SMA":
            window = window or 50
            return await self.get_sma(ticker, window, limit)
        elif indicator_type == "EMA":
            window = window or 50
            return await self.get_ema(ticker, window, limit)
        else:
            raise ValueError(f"Unsupported indicator type: {indicator_type}")
    
    async def get_company_info(self, ticker: str) -> StockInfo:
        """Get company information.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            StockInfo object with company details
        """
        data = await self.polygon.get_ticker_details(ticker)
        return StockInfo.from_polygon_result(data)
    
    async def get_news(
        self,
        ticker: Optional[str] = None,
        limit: int = 10
    ) -> List[NewsArticle]:
        """Get news articles for a ticker or the market.
        
        Args:
            ticker: Stock ticker symbol (optional - if None, gets market news)
            limit: Maximum number of articles to return
            
        Returns:
            List of NewsArticle objects
        """
        data = await self.polygon.get_ticker_news(ticker, limit)
        results = data.get("results", [])
        
        return [NewsArticle.from_polygon_result(r) for r in results]
    
    async def get_dividends(
        self,
        ticker: str,
        limit: int = 10
    ) -> List[Dividend]:
        """Get dividend payment history.
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of dividend records
            
        Returns:
            List of Dividend objects
        """
        data = await self.polygon.get_dividends(ticker, limit)
        results = data.get("results", [])
        
        return [Dividend.from_polygon_result(r) for r in results]
    
    async def get_stock_splits(
        self,
        ticker: str,
        limit: int = 10
    ) -> List[StockSplit]:
        """Get stock split history.
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of split records
            
        Returns:
            List of StockSplit objects
        """
        data = await self.polygon.get_stock_splits(ticker, limit)
        results = data.get("results", [])
        
        return [StockSplit.from_polygon_result(r) for r in results]
    
    async def search_tickers(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, str]]:
        """Search for ticker symbols by company name.
        
        Args:
            query: Search query (company name or partial ticker)
            limit: Maximum number of results
            
        Returns:
            List of dictionaries with ticker and name
        """
        data = await self.polygon.search_tickers(query, limit=limit)
        results = data.get("results", [])
        
        return [
            {
                "ticker": r.get("ticker", ""),
                "name": r.get("name", "Unknown")
            }
            for r in results
        ]
    
    async def get_market_status(self) -> Dict[str, Any]:
        """Get current market status.
        
        Returns:
            Dictionary with market status information
        """
        return await self.polygon.get_market_status()
    
    async def is_market_open(self) -> bool:
        """Check if the stock market is currently open.
        
        Returns:
            True if market is open, False otherwise
        """
        try:
            status = await self.get_market_status()
            exchanges = status.get("exchanges", {})
            
            # Check if any major exchange is open
            nyse = exchanges.get("nyse", "")
            nasdaq = exchanges.get("nasdaq", "")
            
            return nyse == "open" or nasdaq == "open"
        except Exception as e:
            logger.error(f"Error checking market status: {e}")
            return False
    
    async def close(self):
        """Close the underlying Polygon handler session."""
        await self.polygon.close()
