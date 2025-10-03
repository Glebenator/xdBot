# utils/stock_embeds.py
"""Discord embed builders for stock data.

This module provides centralized embed creation for all stock-related commands.
All embeds use consistent styling, colors, and formatting through this builder.
"""

from __future__ import annotations

import discord
from utils.stock_models import (
    StockPrice, IndicatorValue, TradingSignal, StockInfo,
    MACDIndicator, NewsArticle, Dividend, StockSplit
)
from utils.stock_formatters import StockFormatter
from utils.helpers import create_embed
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class StockEmbedBuilder:
    """Build Discord embeds for stock data with consistent styling."""
    
    def __init__(self):
        """Initialize the embed builder."""
        self.formatter = StockFormatter()
    
    def build_price_embed(self, price: StockPrice) -> discord.Embed:
        """Build embed for stock price display.
        
        Args:
            price: StockPrice object
            
        Returns:
            Discord embed with formatted price information
        """
        color = discord.Color.green() if price.is_bullish else discord.Color.red()
        
        embed = create_embed(
            title=f"📊 {price.ticker}",
            color=color.value
        )
        
        # Current price and change
        embed.add_field(
            name="Current Price",
            value=self.formatter.format_price(price.close),
            inline=True
        )
        
        embed.add_field(
            name="Change",
            value=f"{self.formatter.format_price(price.change)} ({self.formatter.format_percentage(price.change_percent)})",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer
        
        # OHLC data
        embed.add_field(
            name="Open",
            value=self.formatter.format_price(price.open),
            inline=True
        )
        
        embed.add_field(
            name="High",
            value=self.formatter.format_price(price.high),
            inline=True
        )
        
        embed.add_field(
            name="Low",
            value=self.formatter.format_price(price.low),
            inline=True
        )
        
        # Volume
        embed.add_field(
            name="Volume",
            value=self.formatter.format_volume(price.volume),
            inline=False
        )
        
        # Timestamp footer
        embed.set_footer(
            text=f"Data from {self.formatter.format_datetime(price.timestamp)}"
        )
        
        return embed
    
    def build_rsi_embed(
        self,
        ticker: str,
        current_price: StockPrice,
        rsi: IndicatorValue,
        signal: TradingSignal,
        history: Optional[List[IndicatorValue]] = None
    ) -> discord.Embed:
        """Build embed for RSI indicator display.
        
        Args:
            ticker: Stock ticker symbol
            current_price: Current price data
            rsi: Current RSI value
            signal: Trading signal from RSI analysis
            history: Optional list of recent RSI values
            
        Returns:
            Discord embed with RSI information
        """
        color = self._get_signal_color(signal)
        
        embed = create_embed(
            title=f"{signal.emoji} {ticker} - RSI Indicator",
            description=signal.reason,
            color=color.value
        )
        
        # RSI value
        window_str = f" ({rsi.window}-day)" if rsi.window else ""
        embed.add_field(
            name=f"RSI{window_str}",
            value=f"**{rsi.value:.2f}**",
            inline=True
        )
        
        # Current price
        embed.add_field(
            name="Current Price",
            value=self.formatter.format_price(current_price.close),
            inline=True
        )
        
        # Signal
        embed.add_field(
            name="Signal",
            value=f"{signal.emoji} **{signal.signal}**",
            inline=True
        )
        
        # Add historical data if provided
        if history and len(history) > 1:
            history_str = " → ".join([f"{h.value:.1f}" for h in reversed(history[-5:])])
            embed.add_field(
                name="5-Day History",
                value=history_str,
                inline=False
            )
        
        # Interpretation guide
        embed.add_field(
            name="RSI Guide",
            value="🔴 >70: Overbought | 🟡 30-70: Neutral | 🟢 <30: Oversold",
            inline=False
        )
        
        return embed
    
    def build_sma_embed(
        self,
        ticker: str,
        current_price: StockPrice,
        sma: IndicatorValue,
        signal: TradingSignal
    ) -> discord.Embed:
        """Build embed for SMA indicator display.
        
        Args:
            ticker: Stock ticker symbol
            current_price: Current price data
            sma: Current SMA value
            signal: Trading signal from SMA analysis
            
        Returns:
            Discord embed with SMA information
        """
        color = self._get_signal_color(signal)
        
        embed = create_embed(
            title=f"{signal.emoji} {ticker} - SMA Indicator",
            description=signal.reason,
            color=color.value
        )
        
        # SMA value
        window_str = f" ({sma.window}-day)" if sma.window else ""
        embed.add_field(
            name=f"SMA{window_str}",
            value=self.formatter.format_price(sma.value),
            inline=True
        )
        
        # Current price
        embed.add_field(
            name="Current Price",
            value=self.formatter.format_price(current_price.close),
            inline=True
        )
        
        # Distance from SMA
        distance = ((current_price.close - sma.value) / sma.value) * 100
        distance_emoji = "📈" if distance > 0 else "📉"
        embed.add_field(
            name="Distance from SMA",
            value=f"{distance_emoji} {distance:+.2f}%",
            inline=True
        )
        
        # Signal
        embed.add_field(
            name="Trend Signal",
            value=f"{signal.emoji} **{signal.signal}**",
            inline=False
        )
        
        return embed
    
    def build_ema_embed(
        self,
        ticker: str,
        current_price: StockPrice,
        ema: IndicatorValue,
        signal: TradingSignal
    ) -> discord.Embed:
        """Build embed for EMA indicator display.
        
        Args:
            ticker: Stock ticker symbol
            current_price: Current price data
            ema: Current EMA value
            signal: Trading signal from EMA analysis
            
        Returns:
            Discord embed with EMA information
        """
        color = self._get_signal_color(signal)
        
        embed = create_embed(
            title=f"{signal.emoji} {ticker} - EMA Indicator",
            description=signal.reason,
            color=color.value
        )
        
        # EMA value
        window_str = f" ({ema.window}-day)" if ema.window else ""
        embed.add_field(
            name=f"EMA{window_str}",
            value=self.formatter.format_price(ema.value),
            inline=True
        )
        
        # Current price
        embed.add_field(
            name="Current Price",
            value=self.formatter.format_price(current_price.close),
            inline=True
        )
        
        # Distance from EMA
        distance = ((current_price.close - ema.value) / ema.value) * 100
        distance_emoji = "📈" if distance > 0 else "📉"
        embed.add_field(
            name="Distance from EMA",
            value=f"{distance_emoji} {distance:+.2f}%",
            inline=True
        )
        
        # Signal
        embed.add_field(
            name="Trend Signal",
            value=f"{signal.emoji} **{signal.signal}**",
            inline=False
        )
        
        return embed
    
    def build_macd_embed(
        self,
        ticker: str,
        current_price: StockPrice,
        macd: MACDIndicator,
        signal: TradingSignal,
        crossover: Optional[str] = None
    ) -> discord.Embed:
        """Build embed for MACD indicator display.
        
        Args:
            ticker: Stock ticker symbol
            current_price: Current price data
            macd: MACD indicator values
            signal: Trading signal from MACD analysis
            crossover: Optional crossover type ('BULLISH_CROSS', 'BEARISH_CROSS')
            
        Returns:
            Discord embed with MACD information
        """
        color = self._get_signal_color(signal)
        
        # Add crossover alert to title if present
        title_prefix = signal.emoji
        if crossover == "BULLISH_CROSS":
            title_prefix = "🚀"
        elif crossover == "BEARISH_CROSS":
            title_prefix = "⚠️"
        
        embed = create_embed(
            title=f"{title_prefix} {ticker} - MACD Indicator",
            description=signal.reason,
            color=color.value
        )
        
        # MACD line
        embed.add_field(
            name="MACD",
            value=f"{macd.macd:.2f}",
            inline=True
        )
        
        # Signal line
        embed.add_field(
            name="Signal Line",
            value=f"{macd.signal:.2f}",
            inline=True
        )
        
        # Histogram
        histogram_emoji = "📈" if macd.histogram > 0 else "📉"
        embed.add_field(
            name="Histogram",
            value=f"{histogram_emoji} {macd.histogram:.2f}",
            inline=True
        )
        
        # Current price
        embed.add_field(
            name="Current Price",
            value=self.formatter.format_price(current_price.close),
            inline=True
        )
        
        # Momentum direction
        momentum = "Bullish 📈" if macd.is_bullish else "Bearish 📉"
        embed.add_field(
            name="Momentum",
            value=momentum,
            inline=True
        )
        
        # Signal
        embed.add_field(
            name="Signal",
            value=f"{signal.emoji} **{signal.signal}**",
            inline=True
        )
        
        # Crossover alert
        if crossover:
            alert_text = "🚀 **Bullish crossover detected!**" if crossover == "BULLISH_CROSS" else "⚠️ **Bearish crossover detected!**"
            embed.add_field(
                name="Crossover Alert",
                value=alert_text,
                inline=False
            )
        
        return embed
    
    def build_company_info_embed(
        self,
        info: StockInfo,
        price: StockPrice
    ) -> discord.Embed:
        """Build embed for company information display.
        
        Args:
            info: Company information
            price: Current price data
            
        Returns:
            Discord embed with company details
        """
        embed = create_embed(
            title=f"ℹ️ {info.name} ({info.ticker})",
            description=info.description[:1000] if info.description else "No description available"
        )
        
        # Market cap and price
        if info.market_cap:
            embed.add_field(
                name="Market Cap",
                value=self.formatter.format_market_cap(info.market_cap),
                inline=True
            )
        
        embed.add_field(
            name="Current Price",
            value=self.formatter.format_price(price.close),
            inline=True
        )
        
        # Price change
        change_str = f"{self.formatter.format_price(price.change)} ({self.formatter.format_percentage(price.change_percent)})"
        embed.add_field(
            name="Today's Change",
            value=change_str,
            inline=True
        )
        
        # Industry info
        if info.sector:
            embed.add_field(name="Sector", value=info.sector, inline=True)
        
        if info.industry:
            embed.add_field(name="Industry", value=info.industry, inline=True)
        
        if info.employees:
            embed.add_field(
                name="Employees",
                value=self.formatter.format_number(info.employees, decimals=0),
                inline=True
            )
        
        # Website
        if info.website:
            embed.add_field(name="Website", value=info.website, inline=False)
        
        return embed
    
    def _get_signal_color(self, signal: TradingSignal) -> discord.Color:
        """Get Discord color for a trading signal.
        
        Args:
            signal: TradingSignal object
            
        Returns:
            Discord color
        """
        if signal.signal == "BUY":
            return discord.Color.green()
        elif signal.signal == "SELL":
            return discord.Color.red()
        else:
            return discord.Color.gold()
