# utils/stock_formatters.py
"""Centralized formatting utilities for stock data display.

This module provides consistent formatting for prices, percentages, volumes,
and other stock-related values across all commands and embeds.
"""

from __future__ import annotations

from typing import Optional


class StockFormatter:
    """Format stock data for human-readable display."""
    
    @staticmethod
    def format_price(price: float) -> str:
        """Format a price value with dollar sign and thousands separators.
        
        Args:
            price: Price value to format
            
        Returns:
            Formatted string (e.g., "$150.25" or "$1,234.56")
            
        Examples:
            >>> StockFormatter.format_price(150.25)
            '$150.25'
            >>> StockFormatter.format_price(1234.56)
            '$1,234.56'
        """
        return f"${price:,.2f}"
    
    @staticmethod
    def format_percentage(percent: float, include_emoji: bool = True, signed: bool = True) -> str:
        """Format a percentage value with optional emoji and sign.
        
        Args:
            percent: Percentage value to format
            include_emoji: Whether to include trend emoji (📈/📉)
            signed: Whether to include + sign for positive values
            
        Returns:
            Formatted string (e.g., "📈 +5.25%" or "-2.50%")
            
        Examples:
            >>> StockFormatter.format_percentage(5.25)
            '📈 +5.25%'
            >>> StockFormatter.format_percentage(-2.50)
            '📉 -2.50%'
            >>> StockFormatter.format_percentage(5.25, include_emoji=False)
            '+5.25%'
        """
        emoji = ""
        if include_emoji:
            emoji = "📈 " if percent >= 0 else "📉 "
        
        sign = ""
        if signed and percent >= 0:
            sign = "+"
        
        return f"{emoji}{sign}{percent:.2f}%"
    
    @staticmethod
    def format_volume(volume: int, short: bool = True) -> str:
        """Format volume with abbreviations (K, M, B).
        
        Args:
            volume: Volume value to format
            short: Whether to use short format (True) or full format (False)
            
        Returns:
            Formatted string (e.g., "1.5M" or "1,500,000")
            
        Examples:
            >>> StockFormatter.format_volume(1500000)
            '1.50M'
            >>> StockFormatter.format_volume(1500000, short=False)
            '1,500,000'
            >>> StockFormatter.format_volume(2500000000)
            '2.50B'
        """
        if not short:
            return f"{volume:,}"
        
        if volume >= 1_000_000_000:
            return f"{volume / 1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            return f"{volume / 1_000_000:.2f}M"
        elif volume >= 1_000:
            return f"{volume / 1_000:.2f}K"
        return str(volume)
    
    @staticmethod
    def format_market_cap(market_cap: float) -> str:
        """Format market capitalization with abbreviations.
        
        Args:
            market_cap: Market cap value to format
            
        Returns:
            Formatted string (e.g., "$1.5T", "$250.5B")
            
        Examples:
            >>> StockFormatter.format_market_cap(1500000000000)
            '$1.50T'
            >>> StockFormatter.format_market_cap(250500000000)
            '$250.50B'
            >>> StockFormatter.format_market_cap(5000000000)
            '$5.00B'
        """
        if market_cap >= 1_000_000_000_000:
            return f"${market_cap / 1_000_000_000_000:.2f}T"
        elif market_cap >= 1_000_000_000:
            return f"${market_cap / 1_000_000_000:.2f}B"
        elif market_cap >= 1_000_000:
            return f"${market_cap / 1_000_000:.2f}M"
        return f"${market_cap:,.0f}"
    
    @staticmethod
    def format_number(number: float, decimals: int = 2) -> str:
        """Format a generic number with thousands separators.
        
        Args:
            number: Number to format
            decimals: Number of decimal places
            
        Returns:
            Formatted string
            
        Examples:
            >>> StockFormatter.format_number(1234567.89)
            '1,234,567.89'
            >>> StockFormatter.format_number(1234567.89, decimals=0)
            '1,234,568'
        """
        if decimals == 0:
            return f"{number:,.0f}"
        return f"{number:,.{decimals}f}"
    
    @staticmethod
    def format_change(change: float, is_percentage: bool = False) -> str:
        """Format a price or percentage change with color indicators.
        
        Args:
            change: Change value
            is_percentage: Whether this is a percentage value
            
        Returns:
            Formatted string with emoji
            
        Examples:
            >>> StockFormatter.format_change(5.25)
            '📈 +$5.25'
            >>> StockFormatter.format_change(5.25, is_percentage=True)
            '📈 +5.25%'
        """
        emoji = "📈" if change >= 0 else "📉"
        sign = "+" if change >= 0 else ""
        
        if is_percentage:
            return f"{emoji} {sign}{change:.2f}%"
        else:
            return f"{emoji} {sign}${change:.2f}"
    
    @staticmethod
    def format_indicator_value(value: float, indicator_type: str) -> str:
        """Format a technical indicator value based on its type.
        
        Args:
            value: Indicator value
            indicator_type: Type of indicator (RSI, SMA, EMA, MACD, etc.)
            
        Returns:
            Formatted string appropriate for the indicator type
            
        Examples:
            >>> StockFormatter.format_indicator_value(65.5, "RSI")
            '65.50'
            >>> StockFormatter.format_indicator_value(150.25, "SMA")
            '$150.25'
        """
        if indicator_type in ["RSI", "MACD", "MACD_SIGNAL", "MACD_HISTOGRAM"]:
            # These are not prices, just numbers
            return f"{value:.2f}"
        else:
            # SMA, EMA are price-based
            return StockFormatter.format_price(value)
    
    @staticmethod
    def get_signal_color_name(signal: str) -> str:
        """Get color name for a trading signal.
        
        Args:
            signal: Signal type (BUY, SELL, HOLD, NEUTRAL)
            
        Returns:
            Color name string for Discord embeds
            
        Examples:
            >>> StockFormatter.get_signal_color_name("BUY")
            'green'
            >>> StockFormatter.get_signal_color_name("SELL")
            'red'
        """
        signal = signal.upper()
        if signal == "BUY":
            return "green"
        elif signal == "SELL":
            return "red"
        elif signal in ["NEUTRAL", "HOLD"]:
            return "gold"
        return "blue"
    
    @staticmethod
    def format_date(dt, format_str: str = "%Y-%m-%d") -> str:
        """Format a datetime object.
        
        Args:
            dt: datetime object
            format_str: strftime format string
            
        Returns:
            Formatted date string
            
        Examples:
            >>> from datetime import datetime
            >>> dt = datetime(2025, 10, 3, 14, 30)
            >>> StockFormatter.format_date(dt)
            '2025-10-03'
            >>> StockFormatter.format_date(dt, "%B %d, %Y")
            'October 03, 2025'
        """
        return dt.strftime(format_str)
    
    @staticmethod
    def format_datetime(dt, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Format a datetime object with time.
        
        Args:
            dt: datetime object
            format_str: strftime format string
            
        Returns:
            Formatted datetime string
        """
        return dt.strftime(format_str)
