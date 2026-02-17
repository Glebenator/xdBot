# utils/chart_generator.py
"""Generate stock price charts using matplotlib."""

import matplotlib

matplotlib.use('Agg')  # Use non-GUI backend
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generate stock price charts."""

    @staticmethod
    def create_price_chart(
        ticker: str,
        data: List[Dict],
        chart_type: str = "candlestick",
        indicators: Optional[List[str]] = None
    ) -> io.BytesIO:
        """Create a price chart from stock data.

        Args:
            ticker: Stock ticker symbol
            data: List of OHLCV data from Polygon API
            chart_type: Type of chart ("candlestick", "line", or "area")
            indicators: Optional list of indicators to overlay (e.g., ["sma_20", "sma_50"])

        Returns:
            BytesIO buffer containing PNG image
        """
        if not data:
            raise ValueError("No data provided for chart generation")

        # Parse data
        dates = [datetime.fromtimestamp(d.get("t", 0) / 1000) for d in data]
        opens = [d.get("o", 0) for d in data]
        highs = [d.get("h", 0) for d in data]
        lows = [d.get("l", 0) for d in data]
        closes = [d.get("c", 0) for d in data]
        volumes = [d.get("v", 0) for d in data]

        # Create figure with two subplots (price and volume)
        fig, (ax1, ax2) = plt.subplots(
            2, 1,
            figsize=(12, 8),
            gridspec_kw={'height_ratios': [3, 1]},
            sharex=True
        )

        # Style configuration
        fig.patch.set_facecolor('#2b2d31')  # Discord dark background
        ax1.set_facecolor('#1e1f22')
        ax2.set_facecolor('#1e1f22')

        # Plot price data
        if chart_type == "candlestick":
            ChartGenerator._plot_candlesticks(ax1, dates, opens, highs, lows, closes)
        elif chart_type == "area":
            ax1.fill_between(dates, closes, alpha=0.3, color='#5865F2')
            ax1.plot(dates, closes, color='#5865F2', linewidth=2)
        else:  # line chart
            ax1.plot(dates, closes, color='#5865F2', linewidth=2)

        # Add indicators if requested
        if indicators:
            ChartGenerator._add_indicators(ax1, dates, closes, indicators)

        # Plot volume
        colors = ['#57F287' if closes[i] >= opens[i] else '#ED4245'
                  for i in range(len(closes))]
        ax2.bar(dates, volumes, color=colors, alpha=0.5, width=0.8)

        # Format axes
        ax1.set_title(
            f'{ticker.upper()} - {len(data)} Days',
            color='white',
            fontsize=16,
            fontweight='bold',
            pad=20
        )
        ax1.set_ylabel('Price ($)', color='white', fontsize=12)
        ax1.tick_params(colors='white')
        ax1.grid(True, alpha=0.2, color='white')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.spines['left'].set_color('white')
        ax1.spines['bottom'].set_color('white')

        ax2.set_ylabel('Volume', color='white', fontsize=12)
        ax2.set_xlabel('Date', color='white', fontsize=12)
        ax2.tick_params(colors='white')
        ax2.grid(True, alpha=0.2, color='white')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        ax2.spines['left'].set_color('white')
        ax2.spines['bottom'].set_color('white')

        # Format x-axis dates
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # Add price labels
        first_price = closes[0]
        last_price = closes[-1]
        change = last_price - first_price
        change_pct = (change / first_price * 100) if first_price > 0 else 0

        change_color = '#57F287' if change >= 0 else '#ED4245'
        change_text = f"${last_price:.2f} ({change:+.2f}, {change_pct:+.2f}%)"

        ax1.text(
            0.02, 0.98,
            change_text,
            transform=ax1.transAxes,
            color=change_color,
            fontsize=12,
            fontweight='bold',
            verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='#2b2d31', alpha=0.8, edgecolor='none')
        )

        # Tight layout
        plt.tight_layout()

        # Save to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', facecolor=fig.get_facecolor(), dpi=150)
        buffer.seek(0)
        plt.close(fig)

        return buffer

    @staticmethod
    def _plot_candlesticks(ax, dates, opens, highs, lows, closes):
        """Plot candlestick chart."""
        width = 0.6

        for i in range(len(dates)):
            color = '#57F287' if closes[i] >= opens[i] else '#ED4245'

            # Draw high-low line
            ax.plot(
                [dates[i], dates[i]],
                [lows[i], highs[i]],
                color=color,
                linewidth=1,
                solid_capstyle='round'
            )

            # Draw open-close box
            height = abs(closes[i] - opens[i])
            bottom = min(opens[i], closes[i])

            # Convert date to numeric value for rectangle position
            date_num = mdates.date2num(dates[i])

            ax.add_patch(Rectangle(
                (date_num - width/2, bottom),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=1.5
            ))

    @staticmethod
    def _add_indicators(ax, dates, closes, indicators: List[str]):
        """Add technical indicators to the chart."""
        for indicator in indicators:
            if indicator.startswith("sma_"):
                try:
                    period = int(indicator.split("_")[1])
                    sma = ChartGenerator._calculate_sma(closes, period)
                    ax.plot(
                        dates[period-1:],
                        sma,
                        label=f'SMA {period}',
                        linewidth=1.5,
                        alpha=0.7
                    )
                except (ValueError, IndexError):
                    logger.warning(f"Invalid SMA indicator format: {indicator}")

            elif indicator.startswith("ema_"):
                try:
                    period = int(indicator.split("_")[1])
                    ema = ChartGenerator._calculate_ema(closes, period)
                    ax.plot(
                        dates,
                        ema,
                        label=f'EMA {period}',
                        linewidth=1.5,
                        alpha=0.7
                    )
                except (ValueError, IndexError):
                    logger.warning(f"Invalid EMA indicator format: {indicator}")

        if indicators:
            ax.legend(loc='upper left', facecolor='#2b2d31', edgecolor='white', labelcolor='white')

    @staticmethod
    def _calculate_sma(data: List[float], period: int) -> List[float]:
        """Calculate Simple Moving Average."""
        sma = []
        for i in range(period - 1, len(data)):
            sma.append(sum(data[i - period + 1:i + 1]) / period)
        return sma

    @staticmethod
    def _calculate_ema(data: List[float], period: int) -> List[float]:
        """Calculate Exponential Moving Average."""
        ema = []
        multiplier = 2 / (period + 1)

        # Start with SMA
        sma = sum(data[:period]) / period
        ema.append(sma)

        # Calculate EMA
        for i in range(1, len(data)):
            if i < period:
                ema.append(data[i])
            else:
                ema_value = (data[i] - ema[-1]) * multiplier + ema[-1]
                ema.append(ema_value)

        return ema

    @staticmethod
    def create_comparison_chart(ticker_data: Dict[str, List[Dict]]) -> io.BytesIO:
        """Create a comparison chart for multiple tickers.

        Args:
            ticker_data: Dict mapping ticker symbols to their OHLCV data

        Returns:
            BytesIO buffer containing PNG image
        """
        if not ticker_data:
            raise ValueError("No data provided for comparison chart")

        # Create figure
        fig, ax = plt.subplots(figsize=(12, 6))
        fig.patch.set_facecolor('#2b2d31')
        ax.set_facecolor('#1e1f22')

        # Plot each ticker (normalized to percentage change from start)
        colors = ['#5865F2', '#57F287', '#FEE75C', '#ED4245', '#EB459E']

        for idx, (ticker, data) in enumerate(ticker_data.items()):
            if not data:
                continue

            dates = [datetime.fromtimestamp(d.get("t", 0) / 1000) for d in data]
            closes = [d.get("c", 0) for d in data]

            # Normalize to percentage change
            first_price = closes[0]
            pct_changes = [(c / first_price - 1) * 100 for c in closes]

            color = colors[idx % len(colors)]
            ax.plot(dates, pct_changes, label=ticker.upper(), color=color, linewidth=2)

        # Format axes
        ax.set_title(
            'Stock Comparison (% Change)',
            color='white',
            fontsize=16,
            fontweight='bold',
            pad=20
        )
        ax.set_ylabel('Change (%)', color='white', fontsize=12)
        ax.set_xlabel('Date', color='white', fontsize=12)
        ax.tick_params(colors='white')
        ax.grid(True, alpha=0.2, color='white')
        ax.axhline(y=0, color='white', linestyle='--', alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('white')
        ax.spines['bottom'].set_color('white')

        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # Add legend
        ax.legend(
            loc='best',
            facecolor='#2b2d31',
            edgecolor='white',
            labelcolor='white',
            framealpha=0.9
        )

        plt.tight_layout()

        # Save to buffer
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', facecolor=fig.get_facecolor(), dpi=150)
        buffer.seek(0)
        plt.close(fig)

        return buffer
