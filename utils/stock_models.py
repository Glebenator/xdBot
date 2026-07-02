# utils/stock_models.py
"""Data models for stock market data.

This module provides strongly-typed data classes for stock prices, indicators,
company information, and trading signals. These models provide a clean abstraction
over the raw API responses and centralize business logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StockPrice:
    """Represents OHLCV (Open, High, Low, Close, Volume) price data for a stock.

    This model provides convenient properties for calculating price changes
    and determining market sentiment.
    """
    ticker: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @property
    def change(self) -> float:
        """Calculate absolute price change from open to close."""
        return self.close - self.open

    @property
    def change_percent(self) -> float:
        """Calculate percentage change from open to close."""
        return (self.change / self.open * 100) if self.open > 0 else 0.0

    @property
    def is_bullish(self) -> bool:
        """Check if the price moved up (close >= open)."""
        return self.close >= self.open

    @property
    def range(self) -> float:
        """Calculate the price range (high - low)."""
        return self.high - self.low

    @property
    def range_percent(self) -> float:
        """Calculate the price range as a percentage of open."""
        return (self.range / self.open * 100) if self.open > 0 else 0.0

    @classmethod
    def from_polygon_result(cls, ticker: str, data: Dict[str, Any]) -> StockPrice:
        """Parse a Polygon API result into a StockPrice object.

        Args:
            ticker: Stock ticker symbol
            data: Raw dictionary from Polygon API with keys: t, o, h, l, c, v

        Returns:
            StockPrice instance

        Example:
            >>> data = {"t": 1609459200000, "o": 150.0, "h": 155.0, "l": 149.0, "c": 154.0, "v": 1000000}
            >>> price = StockPrice.from_polygon_result("AAPL", data)
        """
        return cls(
            ticker=ticker.upper(),
            timestamp=datetime.fromtimestamp(data.get("t", 0) / 1000),
            open=float(data.get("o", 0)),
            high=float(data.get("h", 0)),
            low=float(data.get("l", 0)),
            close=float(data.get("c", 0)),
            volume=int(data.get("v", 0))
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "change": self.change,
            "change_percent": self.change_percent
        }


@dataclass
class IndicatorValue:
    """Represents a single technical indicator value at a point in time.

    This model is used for all technical indicators (RSI, SMA, EMA, MACD, etc.)
    and provides a consistent interface for working with indicator data.
    """
    ticker: str
    timestamp: datetime
    value: float
    indicator_type: str  # 'RSI', 'SMA', 'EMA', 'MACD', 'MACD_SIGNAL', 'MACD_HISTOGRAM'
    window: Optional[int] = None

    @classmethod
    def from_polygon_result(
        cls,
        ticker: str,
        data: Dict[str, Any],
        indicator_type: str,
        window: Optional[int] = None
    ) -> IndicatorValue:
        """Parse a Polygon API indicator result into an IndicatorValue object.

        Args:
            ticker: Stock ticker symbol
            data: Raw dictionary from Polygon API with keys: timestamp, value
            indicator_type: Type of indicator (RSI, SMA, EMA, etc.)
            window: Optional window/period for the indicator

        Returns:
            IndicatorValue instance
        """
        # Handle different timestamp formats
        timestamp_ms = data.get("timestamp", 0)
        if timestamp_ms == 0:
            timestamp_ms = data.get("t", 0)

        # Convert milliseconds to seconds if needed
        if timestamp_ms > 1e12:  # Likely milliseconds
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000)
        else:
            timestamp = datetime.fromtimestamp(timestamp_ms)

        return cls(
            ticker=ticker.upper(),
            timestamp=timestamp,
            value=float(data.get("value", 0)),
            indicator_type=indicator_type,
            window=window
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "indicator_type": self.indicator_type,
            "window": self.window
        }


@dataclass
class MACDIndicator:
    """Represents a MACD indicator with all its components.

    MACD has three values: the MACD line, signal line, and histogram.
    This model keeps them together for easier analysis.
    """
    ticker: str
    timestamp: datetime
    macd: float
    signal: float
    histogram: float

    @property
    def is_bullish(self) -> bool:
        """Check if MACD is showing bullish signal (MACD > signal)."""
        return self.macd > self.signal

    @property
    def is_bearish(self) -> bool:
        """Check if MACD is showing bearish signal (MACD < signal)."""
        return self.macd < self.signal

    @classmethod
    def from_polygon_result(cls, ticker: str, data: Dict[str, Any]) -> MACDIndicator:
        """Parse a Polygon API MACD result into a MACDIndicator object.

        Args:
            ticker: Stock ticker symbol
            data: Raw dictionary from Polygon API

        Returns:
            MACDIndicator instance
        """
        timestamp_ms = data.get("timestamp", data.get("t", 0))
        if timestamp_ms > 1e12:
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000)
        else:
            timestamp = datetime.fromtimestamp(timestamp_ms)

        return cls(
            ticker=ticker.upper(),
            timestamp=timestamp,
            macd=float(data.get("value", 0)),
            signal=float(data.get("signal", 0)),
            histogram=float(data.get("histogram", 0))
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "timestamp": self.timestamp.isoformat(),
            "macd": self.macd,
            "signal": self.signal,
            "histogram": self.histogram
        }


@dataclass
class StockInfo:
    """Represents detailed company information for a stock.

    This model contains fundamental data about a company including
    name, description, market cap, and other identifying information.
    """
    ticker: str
    name: str
    description: str
    market_cap: Optional[float] = None
    website: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    employees: Optional[int] = None

    @classmethod
    def from_polygon_result(cls, data: Dict[str, Any]) -> StockInfo:
        """Parse a Polygon API ticker details result into a StockInfo object.

        Args:
            data: Raw dictionary from Polygon API ticker details endpoint

        Returns:
            StockInfo instance
        """
        results = data.get("results", {})
        return cls(
            ticker=results.get("ticker", "").upper(),
            name=results.get("name", "Unknown"),
            description=results.get("description", "No description available"),
            market_cap=results.get("market_cap"),
            website=results.get("homepage_url"),
            sector=results.get("sic_description"),
            industry=results.get("industry"),
            employees=results.get("total_employees")
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "description": self.description,
            "market_cap": self.market_cap,
            "website": self.website,
            "sector": self.sector,
            "industry": self.industry,
            "employees": self.employees
        }


@dataclass
class TradingSignal:
    """Represents a trading signal derived from technical analysis.

    This model encapsulates buy/sell/hold recommendations with
    strength indicators and human-readable explanations.
    """
    signal: str  # 'BUY', 'SELL', 'HOLD', 'NEUTRAL'
    strength: float  # 0.0 to 1.0, where 1.0 is strongest
    reason: str  # Human-readable explanation
    emoji: str  # Visual indicator

    @property
    def is_strong(self) -> bool:
        """Check if this is a strong signal (strength > 0.7)."""
        return self.strength > 0.7

    @property
    def is_weak(self) -> bool:
        """Check if this is a weak signal (strength < 0.3)."""
        return self.strength < 0.3

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "signal": self.signal,
            "strength": self.strength,
            "reason": self.reason,
            "emoji": self.emoji
        }


@dataclass
class NewsArticle:
    """Represents a news article about a stock or the market.

    This model provides structured access to news data from the API.
    """
    title: str
    publisher: str
    published_date: datetime
    article_url: str
    image_url: Optional[str] = None
    description: Optional[str] = None
    tickers: Optional[List[str]] = None

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.tickers is None:
            self.tickers = []

    @classmethod
    def from_polygon_result(cls, data: Dict[str, Any]) -> NewsArticle:
        """Parse a Polygon API news result into a NewsArticle object.

        Args:
            data: Raw dictionary from Polygon API news endpoint

        Returns:
            NewsArticle instance
        """
        published_str = data.get("published_utc", "")
        try:
            published_date = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            published_date = datetime.now()

        return cls(
            title=data.get("title", "No title"),
            publisher=data.get("publisher", {}).get("name", "Unknown"),
            published_date=published_date,
            article_url=data.get("article_url", ""),
            image_url=data.get("image_url"),
            description=data.get("description"),
            tickers=data.get("tickers", [])
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "publisher": self.publisher,
            "published_date": self.published_date.isoformat(),
            "article_url": self.article_url,
            "image_url": self.image_url,
            "description": self.description,
            "tickers": self.tickers
        }


@dataclass
class Dividend:
    """Represents a dividend payment."""
    ticker: str
    ex_dividend_date: datetime
    payment_date: datetime
    amount: float

    @classmethod
    def from_polygon_result(cls, data: Dict[str, Any]) -> Dividend:
        """Parse a Polygon API dividend result into a Dividend object."""
        return cls(
            ticker=data.get("ticker", "").upper(),
            ex_dividend_date=datetime.fromisoformat(data.get("ex_dividend_date", "")),
            payment_date=datetime.fromisoformat(data.get("pay_date", "")),
            amount=float(data.get("cash_amount", 0))
        )


@dataclass
class StockSplit:
    """Represents a stock split event."""
    ticker: str
    execution_date: datetime
    split_from: float
    split_to: float

    @property
    def split_ratio(self) -> str:
        """Get the split ratio as a string (e.g., '2-for-1')."""
        return f"{self.split_to:.0f}-for-{self.split_from:.0f}"

    @classmethod
    def from_polygon_result(cls, data: Dict[str, Any]) -> StockSplit:
        """Parse a Polygon API stock split result into a StockSplit object."""
        return cls(
            ticker=data.get("ticker", "").upper(),
            execution_date=datetime.fromisoformat(data.get("execution_date", "")),
            split_from=float(data.get("split_from", 1)),
            split_to=float(data.get("split_to", 1))
        )
