# utils/indicator_analyzer.py
"""Technical indicator analysis and signal generation.

This module provides centralized logic for analyzing technical indicators
and generating trading signals. All signal interpretation is done here
to maintain consistency across commands and tools.
"""

from __future__ import annotations

from utils.stock_models import IndicatorValue, TradingSignal, StockPrice, MACDIndicator
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class IndicatorAnalyzer:
    """Analyze technical indicators and generate trading signals."""
    
    @staticmethod
    def analyze_rsi(rsi_value: float, window: int = 14) -> TradingSignal:
        """Analyze RSI (Relative Strength Index) and return trading signal.
        
        RSI Scale:
        - > 70: Overbought (potential sell signal)
        - < 30: Oversold (potential buy signal)
        - 30-70: Neutral range
        
        Args:
            rsi_value: RSI value (0-100)
            window: RSI window period (default 14)
            
        Returns:
            TradingSignal with recommendation
            
        Examples:
            >>> signal = IndicatorAnalyzer.analyze_rsi(75.5)
            >>> signal.signal
            'SELL'
            >>> signal = IndicatorAnalyzer.analyze_rsi(25.0)
            >>> signal.signal
            'BUY'
        """
        if rsi_value > 70:
            # Overbought - potential sell
            strength = min((rsi_value - 70) / 30, 1.0)  # 0-1 scale based on how overbought
            return TradingSignal(
                signal="SELL",
                strength=strength,
                reason=f"Overbought (RSI {rsi_value:.1f} > 70)",
                emoji="🔴"
            )
        elif rsi_value < 30:
            # Oversold - potential buy
            strength = min((30 - rsi_value) / 30, 1.0)  # 0-1 scale based on how oversold
            return TradingSignal(
                signal="BUY",
                strength=strength,
                reason=f"Oversold (RSI {rsi_value:.1f} < 30)",
                emoji="🟢"
            )
        else:
            # Neutral range
            # Calculate how close to neutral (50) - closer = weaker signal
            distance_from_neutral = abs(rsi_value - 50)
            strength = 1.0 - (distance_from_neutral / 20)  # Max 0.5 for neutral
            
            return TradingSignal(
                signal="NEUTRAL",
                strength=max(0.3, strength),
                reason=f"Neutral range (RSI {rsi_value:.1f})",
                emoji="🟡"
            )
    
    @staticmethod
    def analyze_moving_average(
        current_price: float,
        ma_value: float,
        ma_type: str = "SMA",
        window: int = 50
    ) -> TradingSignal:
        """Analyze price position relative to moving average.
        
        Price above MA = Uptrend (bullish)
        Price below MA = Downtrend (bearish)
        
        Args:
            current_price: Current stock price
            ma_value: Moving average value
            ma_type: Type of MA (SMA or EMA)
            window: MA window period
            
        Returns:
            TradingSignal with recommendation
        """
        distance = current_price - ma_value
        distance_percent = (distance / ma_value) * 100
        
        # Strength based on distance from MA (capped at 10%)
        strength = min(abs(distance_percent) / 10, 1.0)
        
        if current_price > ma_value:
            # Price above MA - bullish
            return TradingSignal(
                signal="BUY",
                strength=strength,
                reason=f"Price {distance_percent:+.2f}% above {window}-day {ma_type}",
                emoji="📈"
            )
        else:
            # Price below MA - bearish
            return TradingSignal(
                signal="SELL",
                strength=strength,
                reason=f"Price {distance_percent:.2f}% below {window}-day {ma_type}",
                emoji="📉"
            )
    
    @staticmethod
    def analyze_macd(macd_indicator: MACDIndicator) -> TradingSignal:
        """Analyze MACD (Moving Average Convergence Divergence).
        
        MACD Signals:
        - MACD > Signal: Bullish
        - MACD < Signal: Bearish
        - Histogram: Shows momentum strength
        
        Args:
            macd_indicator: MACDIndicator object with macd, signal, histogram
            
        Returns:
            TradingSignal with recommendation
        """
        macd = macd_indicator.macd
        signal = macd_indicator.signal
        histogram = macd_indicator.histogram
        
        # Strength based on histogram magnitude (normalized)
        strength = min(abs(histogram) / 5, 1.0)
        
        if histogram > 0 and macd > signal:
            # Bullish - MACD above signal
            emoji = "🚀" if strength > 0.7 else "📈"
            return TradingSignal(
                signal="BUY",
                strength=strength,
                reason=f"Bullish (MACD {macd:.2f} > Signal {signal:.2f})",
                emoji=emoji
            )
        elif histogram < 0 and macd < signal:
            # Bearish - MACD below signal
            emoji = "⚠️" if strength > 0.7 else "📉"
            return TradingSignal(
                signal="SELL",
                strength=strength,
                reason=f"Bearish (MACD {macd:.2f} < Signal {signal:.2f})",
                emoji=emoji
            )
        else:
            # Weak or conflicting signal
            return TradingSignal(
                signal="NEUTRAL",
                strength=0.5,
                reason="No clear signal",
                emoji="➖"
            )
    
    @staticmethod
    def detect_macd_crossover(
        current: MACDIndicator,
        previous: MACDIndicator
    ) -> Optional[str]:
        """Detect MACD crossover events.
        
        Args:
            current: Current MACD values
            previous: Previous MACD values
            
        Returns:
            'BULLISH_CROSS' if MACD crossed above signal,
            'BEARISH_CROSS' if MACD crossed below signal,
            None if no crossover
        """
        # Bullish crossover: MACD crosses above signal
        if previous.macd <= previous.signal and current.macd > current.signal:
            return "BULLISH_CROSS"
        
        # Bearish crossover: MACD crosses below signal
        if previous.macd >= previous.signal and current.macd < current.signal:
            return "BEARISH_CROSS"
        
        return None
    
    @staticmethod
    def detect_golden_cross(
        sma_50_current: float,
        sma_200_current: float,
        sma_50_previous: float,
        sma_200_previous: float
    ) -> Optional[str]:
        """Detect golden cross or death cross pattern.
        
        Golden Cross: 50-day SMA crosses above 200-day SMA (very bullish)
        Death Cross: 50-day SMA crosses below 200-day SMA (very bearish)
        
        Args:
            sma_50_current: Current 50-day SMA
            sma_200_current: Current 200-day SMA
            sma_50_previous: Previous 50-day SMA
            sma_200_previous: Previous 200-day SMA
            
        Returns:
            'GOLDEN_CROSS' for bullish crossover,
            'DEATH_CROSS' for bearish crossover,
            None if no crossover
        """
        # Golden cross: 50 SMA crosses above 200 SMA
        if sma_50_previous <= sma_200_previous and sma_50_current > sma_200_current:
            return "GOLDEN_CROSS"
        
        # Death cross: 50 SMA crosses below 200 SMA
        if sma_50_previous >= sma_200_previous and sma_50_current < sma_200_current:
            return "DEATH_CROSS"
        
        return None
    
    @staticmethod
    def analyze_multi_indicator(
        rsi: Optional[float] = None,
        price_vs_sma: Optional[Tuple[float, float]] = None,
        macd: Optional[MACDIndicator] = None
    ) -> TradingSignal:
        """Combine multiple indicators for a consensus signal.
        
        This provides a more robust signal by considering multiple
        technical indicators together.
        
        Args:
            rsi: RSI value (0-100)
            price_vs_sma: Tuple of (current_price, sma_value)
            macd: MACDIndicator object
            
        Returns:
            Combined TradingSignal
        """
        signals = []
        weights = []
        
        # RSI signal
        if rsi is not None:
            rsi_signal = IndicatorAnalyzer.analyze_rsi(rsi)
            signals.append(rsi_signal)
            weights.append(0.3)  # 30% weight
        
        # Moving average signal
        if price_vs_sma is not None:
            price, sma = price_vs_sma
            ma_signal = IndicatorAnalyzer.analyze_moving_average(price, sma)
            signals.append(ma_signal)
            weights.append(0.4)  # 40% weight
        
        # MACD signal
        if macd is not None:
            macd_signal = IndicatorAnalyzer.analyze_macd(macd)
            signals.append(macd_signal)
            weights.append(0.3)  # 30% weight
        
        if not signals:
            return TradingSignal(
                signal="NEUTRAL",
                strength=0.0,
                reason="No indicators provided",
                emoji="❓"
            )
        
        # Calculate weighted consensus
        buy_score = sum(w for s, w in zip(signals, weights) if s.signal == "BUY")
        sell_score = sum(w for s, w in zip(signals, weights) if s.signal == "SELL")
        
        # Determine final signal
        if buy_score > sell_score and buy_score > 0.5:
            signal = "BUY"
            strength = buy_score
            emoji = "🟢"
        elif sell_score > buy_score and sell_score > 0.5:
            signal = "SELL"
            strength = sell_score
            emoji = "🔴"
        else:
            signal = "NEUTRAL"
            strength = 0.5
            emoji = "🟡"
        
        # Build reason from individual signals
        reasons = [f"{s.emoji} {s.signal}" for s in signals]
        reason = "Combined: " + ", ".join(reasons)
        
        return TradingSignal(
            signal=signal,
            strength=strength,
            reason=reason,
            emoji=emoji
        )
    
    @staticmethod
    def get_rsi_interpretation(rsi_value: float) -> str:
        """Get human-readable interpretation of RSI value.
        
        Args:
            rsi_value: RSI value (0-100)
            
        Returns:
            Interpretation string
        """
        if rsi_value > 80:
            return "Extremely overbought - strong sell signal"
        elif rsi_value > 70:
            return "Overbought - potential sell signal"
        elif rsi_value > 60:
            return "Moderately strong - slight bullish bias"
        elif rsi_value > 40:
            return "Neutral - no clear signal"
        elif rsi_value > 30:
            return "Moderately weak - slight bearish bias"
        elif rsi_value > 20:
            return "Oversold - potential buy signal"
        else:
            return "Extremely oversold - strong buy signal"
    
    @staticmethod
    def get_trend_strength(price_history: List[StockPrice]) -> str:
        """Analyze trend strength from price history.
        
        Args:
            price_history: List of StockPrice objects (newest first)
            
        Returns:
            Trend description string
        """
        if len(price_history) < 5:
            return "Insufficient data"
        
        # Look at last 5 days
        recent = price_history[:5]
        up_days = sum(1 for p in recent if p.is_bullish)
        
        if up_days >= 4:
            return "Strong uptrend"
        elif up_days >= 3:
            return "Moderate uptrend"
        elif up_days == 2:
            return "Consolidating"
        elif up_days == 1:
            return "Moderate downtrend"
        else:
            return "Strong downtrend"
