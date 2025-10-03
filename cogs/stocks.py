# cogs/stocks.py
"""Stock market data commands using Polygon.io API."""

import discord
from discord.ext import commands
from discord import app_commands
from utils.helpers import create_embed, defer_hybrid, send_hybrid_message
from utils.polygon_handler import PolygonHandler
from utils.chart_generator import ChartGenerator
from utils.stock_service import StockService
from utils.stock_embeds import StockEmbedBuilder
from utils.indicator_analyzer import IndicatorAnalyzer
from datetime import datetime, timedelta
from typing import Optional
import logging

import config

logger = logging.getLogger(__name__)


class Stocks(commands.Cog):
    """Commands for fetching stock market data."""
    
    def __init__(self, bot):
        self.bot = bot
        self.polygon_enabled = config.settings.polygon_enabled
        
        if not self.polygon_enabled:
            logger.warning(
                "POLYGON_API_KEY is not configured; stock commands will be unavailable."
            )
        
        # Initialize handlers
        self.polygon = PolygonHandler(config.settings.polygon_api_key)
        self.stock_service = StockService(self.polygon)
        self.embed_builder = StockEmbedBuilder()
    
    async def cog_unload(self):
        """Cleanup when cog is unloaded."""
        await self.polygon.close()
        await self.stock_service.close()
    
    def _create_price_embed(self, data: dict, ticker: str) -> discord.Embed:
        """Create an embed for stock price data.
        
        Args:
            data: Stock data from Polygon API
            ticker: Stock ticker symbol
            
        Returns:
            Discord embed with formatted stock information
        """
        results = data.get("results", [])
        if not results:
            return create_embed(
                title=f"📊 {ticker.upper()}",
                description="No data available",
                color=discord.Color.orange()
            )
        
        result = results[0]
        
        # Extract data
        open_price = result.get("o", 0)
        high_price = result.get("h", 0)
        low_price = result.get("l", 0)
        close_price = result.get("c", 0)
        volume = result.get("v", 0)
        
        # Calculate change
        change = close_price - open_price
        change_percent = (change / open_price * 100) if open_price > 0 else 0
        
        # Determine color based on performance
        color = discord.Color.green() if change >= 0 else discord.Color.red()
        
        embed = create_embed(
            title=f"📊 {ticker.upper()}",
            color=color.value
        )
        
        embed.add_field(
            name="Current Price",
            value=self.polygon.format_price(close_price),
            inline=True
        )
        
        embed.add_field(
            name="Change",
            value=f"{self.polygon.format_price(change)} ({self.polygon.format_percentage(change_percent)})",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer
        
        embed.add_field(
            name="Open",
            value=self.polygon.format_price(open_price),
            inline=True
        )
        
        embed.add_field(
            name="High",
            value=self.polygon.format_price(high_price),
            inline=True
        )
        
        embed.add_field(
            name="Low",
            value=self.polygon.format_price(low_price),
            inline=True
        )
        
        embed.add_field(
            name="Volume",
            value=f"{volume:,}",
            inline=False
        )
        
        # Add timestamp
        timestamp = result.get("t")
        if timestamp:
            dt = datetime.fromtimestamp(timestamp / 1000)
            embed.set_footer(text=f"Data from {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return embed
    
    def _create_snapshot_embed(self, data: dict, ticker: str) -> discord.Embed:
        """Create an embed for stock snapshot data.
        
        Args:
            data: Snapshot data from Polygon API
            ticker: Stock ticker symbol
            
        Returns:
            Discord embed with formatted snapshot information
        """
        ticker_data = data.get("ticker", {})
        day_data = ticker_data.get("day", {})
        prev_day_data = ticker_data.get("prevDay", {})
        
        if not day_data:
            return create_embed(
                title=f"📊 {ticker.upper()}",
                description="No snapshot data available",
                color=discord.Color.orange()
            )
        
        # Extract current day data
        current_price = day_data.get("c", 0)
        open_price = day_data.get("o", 0)
        high_price = day_data.get("h", 0)
        low_price = day_data.get("l", 0)
        volume = day_data.get("v", 0)
        
        # Calculate change
        prev_close = prev_day_data.get("c", open_price)
        change = current_price - prev_close
        change_percent = (change / prev_close * 100) if prev_close > 0 else 0
        
        # Determine color
        color = discord.Color.green() if change >= 0 else discord.Color.red()
        
        embed = create_embed(
            title=f"📊 {ticker.upper()} - Live Snapshot",
            color=color.value
        )
        
        embed.add_field(
            name="Current Price",
            value=self.polygon.format_price(current_price),
            inline=True
        )
        
        embed.add_field(
            name="Change",
            value=f"{self.polygon.format_price(change)} ({self.polygon.format_percentage(change_percent)})",
            inline=True
        )
        
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        embed.add_field(
            name="Open",
            value=self.polygon.format_price(open_price),
            inline=True
        )
        
        embed.add_field(
            name="High",
            value=self.polygon.format_price(high_price),
            inline=True
        )
        
        embed.add_field(
            name="Low",
            value=self.polygon.format_price(low_price),
            inline=True
        )
        
        embed.add_field(
            name="Volume",
            value=f"{volume:,}",
            inline=False
        )
        
        embed.set_footer(text="Real-time snapshot data")
        
        return embed
    
    @commands.hybrid_command(name="stock", aliases=["quote", "price"])
    async def stock_price(self, ctx, ticker: str):
        """Get the latest stock price for a ticker.
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL, TSLA, MSFT)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            # Try previous close first (works on free tier)
            try:
                data = await self.polygon.get_previous_close(ticker)
                embed = self._create_price_embed(data, ticker)
                # Add note about data type
                embed.set_footer(text=f"{embed.footer.text or ''} | Previous close data (snapshot requires paid plan)".strip())
            except Exception as e:
                logger.debug(f"Previous close failed for {ticker}, trying snapshot: {e}")
                
                # Fall back to snapshot (for paid plans)
                data = await self.polygon.get_snapshot(ticker)
                embed = self._create_snapshot_embed(data, ticker)
                
        except Exception as e:
            logger.error(f"Error fetching stock data for {ticker}: {e}")
            
            # Provide helpful error message
            error_msg = str(e)
            if "403" in error_msg or "Forbidden" in error_msg:
                description = (
                    f"Could not fetch data for `{ticker.upper()}`.\n\n"
                    "**Possible reasons:**\n"
                    "• API key may not have access to required endpoints\n"
                    "• Free tier has limited endpoint access\n"
                    "• Check your plan at [polygon.io/dashboard](https://polygon.io/dashboard)"
                )
            else:
                description = f"Could not fetch stock data for `{ticker.upper()}`. Please check the ticker symbol and try again."
            
            embed = create_embed(
                title="❌ Error",
                description=description,
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stockinfo")
    async def stock_info(self, ctx, ticker: str):
        """Get detailed information about a stock ticker.
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL, TSLA, MSFT)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            data = await self.polygon.get_ticker_details(ticker)
            results = data.get("results", {})
            
            if not results:
                embed = create_embed(
                    title="❌ Not Found",
                    description=f"Could not find information for ticker `{ticker.upper()}`",
                    color=discord.Color.red()
                )
            else:
                embed = create_embed(
                    title=f"📈 {results.get('ticker', ticker.upper())}",
                    description=results.get("description", "No description available")[:500],
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Name",
                    value=results.get("name", "N/A"),
                    inline=True
                )
                
                embed.add_field(
                    name="Market",
                    value=results.get("market", "N/A").upper(),
                    inline=True
                )
                
                embed.add_field(
                    name="Type",
                    value=results.get("type", "N/A"),
                    inline=True
                )
                
                if "primary_exchange" in results:
                    embed.add_field(
                        name="Exchange",
                        value=results["primary_exchange"],
                        inline=True
                    )
                
                if "currency_name" in results:
                    embed.add_field(
                        name="Currency",
                        value=results["currency_name"],
                        inline=True
                    )
                
                if "locale" in results:
                    embed.add_field(
                        name="Locale",
                        value=results["locale"].upper(),
                        inline=True
                    )
                
                if "homepage_url" in results:
                    embed.add_field(
                        name="Website",
                        value=f"[Visit]({results['homepage_url']})",
                        inline=False
                    )
                
                # Add logo if available
                if "icon_url" in results:
                    embed.set_thumbnail(url=results["icon_url"])
        
        except Exception as e:
            logger.error(f"Error fetching ticker details for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not fetch information for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stocksearch")
    async def stock_search(self, ctx, *, query: str):
        """Search for stock tickers by name or symbol.
        
        Args:
            query: Search query (company name or ticker symbol)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            data = await self.polygon.search_tickers(query, limit=10)
            results = data.get("results", [])
            
            if not results:
                embed = create_embed(
                    title="🔍 No Results",
                    description=f"No tickers found matching `{query}`",
                    color=discord.Color.orange()
                )
            else:
                embed = create_embed(
                    title=f"🔍 Search Results for '{query}'",
                    description=f"Found {len(results)} ticker(s)",
                    color=discord.Color.blue()
                )
                
                for result in results[:10]:
                    ticker = result.get("ticker", "N/A")
                    name = result.get("name", "N/A")
                    market = result.get("market", "N/A")
                    
                    embed.add_field(
                        name=f"{ticker} - {name}",
                        value=f"Market: {market.upper()}",
                        inline=False
                    )
        
        except Exception as e:
            logger.error(f"Error searching tickers for '{query}': {e}")
            embed = create_embed(
                title="❌ Error",
                description="An error occurred while searching. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="marketstatus")
    async def market_status(self, ctx):
        """Get the current market status (open/closed)."""
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            data = await self.polygon.get_market_status()
            
            market = data.get("market", "unknown")
            server_time = data.get("serverTime", "N/A")
            
            exchanges = data.get("exchanges", {})
            nyse = exchanges.get("nyse", "unknown")
            nasdaq = exchanges.get("nasdaq", "unknown")
            otc = exchanges.get("otc", "unknown")
            
            # Create status emoji
            status_emoji = {
                "open": "🟢",
                "closed": "🔴",
                "extended-hours": "🟡"
            }
            
            embed = create_embed(
                title="📊 Market Status",
                description=f"Server Time: {server_time}",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Overall Market",
                value=f"{status_emoji.get(market, '⚪')} {market.upper()}",
                inline=False
            )
            
            embed.add_field(
                name="NYSE",
                value=f"{status_emoji.get(nyse, '⚪')} {nyse.upper()}",
                inline=True
            )
            
            embed.add_field(
                name="NASDAQ",
                value=f"{status_emoji.get(nasdaq, '⚪')} {nasdaq.upper()}",
                inline=True
            )
            
            embed.add_field(
                name="OTC",
                value=f"{status_emoji.get(otc, '⚪')} {otc.upper()}",
                inline=True
            )
        
        except Exception as e:
            logger.error(f"Error fetching market status: {e}")
            embed = create_embed(
                title="❌ Error",
                description="Could not fetch market status. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stocknews")
    async def stock_news(self, ctx, ticker: Optional[str] = None, limit: int = 5):
        """Get recent news articles for a stock or the market.
        
        Args:
            ticker: Stock ticker symbol (optional - shows market news if omitted)
            limit: Number of articles (default 5, max 10)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        limit = min(limit, 10)  # Cap at 10
        
        try:
            data = await self.polygon.get_ticker_news(ticker, limit=limit)
            results = data.get("results", [])
            
            if not results:
                embed = create_embed(
                    title="📰 No News Found",
                    description=f"No recent news for {ticker.upper() if ticker else 'the market'}",
                    color=discord.Color.orange()
                )
            else:
                title = f"📰 News: {ticker.upper()}" if ticker else "📰 Market News"
                embed = create_embed(
                    title=title,
                    description=f"Latest {len(results)} article(s)",
                    color=discord.Color.blue()
                )
                
                for article in results[:limit]:
                    title_text = article.get("title", "No title")
                    url = article.get("article_url", "")
                    published = article.get("published_utc", "")
                    author = article.get("author", "Unknown")
                    
                    # Format published date
                    try:
                        pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                        date_str = pub_date.strftime("%Y-%m-%d %H:%M")
                    except:
                        date_str = published
                    
                    value = f"[Read article]({url})\n📅 {date_str} | ✍️ {author}"
                    
                    embed.add_field(
                        name=title_text[:256],  # Discord field name limit
                        value=value[:1024],  # Discord field value limit
                        inline=False
                    )
        
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            embed = create_embed(
                title="❌ Error",
                description="Could not fetch news. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stockdividends")
    async def stock_dividends(self, ctx, ticker: str, limit: int = 5):
        """Get dividend history for a stock.
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
            limit: Number of dividends to show (default 5, max 10)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        limit = min(limit, 10)
        
        try:
            data = await self.polygon.get_dividends(ticker, limit=limit)
            results = data.get("results", [])
            
            if not results:
                embed = create_embed(
                    title=f"💰 {ticker.upper()} - Dividends",
                    description="No dividend data found",
                    color=discord.Color.orange()
                )
            else:
                embed = create_embed(
                    title=f"💰 {ticker.upper()} - Dividend History",
                    description=f"Last {len(results)} dividend(s)",
                    color=discord.Color.green()
                )
                
                for div in results:
                    ex_date = div.get("ex_dividend_date", "N/A")
                    pay_date = div.get("pay_date", "N/A")
                    amount = div.get("cash_amount", 0)
                    
                    embed.add_field(
                        name=f"${amount:.4f} per share",
                        value=f"Ex-Date: {ex_date}\nPay Date: {pay_date}",
                        inline=True
                    )
        
        except Exception as e:
            logger.error(f"Error fetching dividends for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not fetch dividend data for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stocksplits")
    async def stock_splits(self, ctx, ticker: str, limit: int = 5):
        """Get stock split history for a stock.
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
            limit: Number of splits to show (default 5, max 10)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        limit = min(limit, 10)
        
        try:
            data = await self.polygon.get_stock_splits(ticker, limit=limit)
            results = data.get("results", [])
            
            if not results:
                embed = create_embed(
                    title=f"🔀 {ticker.upper()} - Stock Splits",
                    description="No stock split data found",
                    color=discord.Color.orange()
                )
            else:
                embed = create_embed(
                    title=f"🔀 {ticker.upper()} - Stock Split History",
                    description=f"Last {len(results)} split(s)",
                    color=discord.Color.blue()
                )
                
                for split in results:
                    ex_date = split.get("execution_date", "N/A")
                    split_from = split.get("split_from", 1)
                    split_to = split.get("split_to", 1)
                    
                    ratio = f"{split_to}:{split_from}"
                    
                    embed.add_field(
                        name=f"{ratio} Split",
                        value=f"Date: {ex_date}",
                        inline=True
                    )
        
        except Exception as e:
            logger.error(f"Error fetching splits for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not fetch split data for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stockchart")
    async def stock_chart(
        self,
        ctx,
        ticker: str,
        days: int = 30,
        chart_type: str = "candlestick",
        indicators: Optional[str] = None
    ):
        """Generate a visual price chart for a stock.
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
            days: Number of days of history (default 30, max 365)
            chart_type: Chart style: candlestick, line, or area (default candlestick)
            indicators: Optional indicators like "sma_20,sma_50" or "ema_12,ema_26"
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        # Validate chart type
        valid_types = ["candlestick", "line", "area"]
        if chart_type.lower() not in valid_types:
            chart_type = "candlestick"
        
        # Parse indicators
        indicator_list = []
        if indicators:
            indicator_list = [i.strip() for i in indicators.split(",")]
        
        days = min(days, 365)  # Cap at 1 year
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            data = await self.polygon.get_aggregates(
                ticker,
                timespan="day",
                from_date=from_date,
                to_date=to_date
            )
            results = data.get("results", [])
            
            if not results:
                embed = create_embed(
                    title=f"📈 {ticker.upper()} - Chart",
                    description="No historical data available for charting",
                    color=discord.Color.orange()
                )
                await send_hybrid_message(ctx, embed=embed)
                return
            
            # Generate chart
            chart_buffer = ChartGenerator.create_price_chart(
                ticker=ticker,
                data=results,
                chart_type=chart_type.lower(),
                indicators=indicator_list
            )
            
            # Calculate stats for embed
            prices = [r.get("c", 0) for r in results]
            first = prices[0]
            last = prices[-1]
            change = last - first
            change_pct = (change / first * 100) if first > 0 else 0
            
            color = discord.Color.green() if change >= 0 else discord.Color.red()
            
            embed = create_embed(
                title=f"📈 {ticker.upper()} - {days} Day Chart",
                description=f"{chart_type.capitalize()} chart with {len(results)} trading days",
                color=color.value
            )
            
            change_emoji = "📈" if change >= 0 else "📉"
            embed.add_field(
                name="Price Change",
                value=f"{change_emoji} {self.polygon.format_price(change)} ({self.polygon.format_percentage(change_pct)})",
                inline=False
            )
            
            if indicator_list:
                embed.add_field(
                    name="Indicators",
                    value=", ".join(indicator_list),
                    inline=False
                )
            
            # Create file from buffer
            file = discord.File(chart_buffer, filename=f"{ticker.upper()}_chart.png")
            embed.set_image(url=f"attachment://{ticker.upper()}_chart.png")
            
            await send_hybrid_message(ctx, embed=embed, file=file)
        
        except Exception as e:
            logger.error(f"Error generating chart for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not generate chart for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stockcompare")
    async def stock_compare(self, ctx, tickers: str, days: int = 30):
        """Compare performance of multiple stocks.
        
        Args:
            tickers: Comma-separated ticker symbols (e.g., AAPL,MSFT,GOOGL)
            days: Number of days to compare (default 30, max 365)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        # Parse tickers
        ticker_list = [t.strip().upper() for t in tickers.split(",")]
        if len(ticker_list) > 5:
            embed = create_embed(
                title="❌ Too Many Tickers",
                description="Please compare a maximum of 5 stocks at a time.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        days = min(days, 365)
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Fetch data for all tickers
            ticker_data = {}
            performance = []
            
            for ticker in ticker_list:
                data = await self.polygon.get_aggregates(
                    ticker,
                    timespan="day",
                    from_date=from_date,
                    to_date=to_date
                )
                results = data.get("results", [])
                
                if results:
                    ticker_data[ticker] = results
                    prices = [r.get("c", 0) for r in results]
                    change_pct = ((prices[-1] - prices[0]) / prices[0] * 100) if prices[0] > 0 else 0
                    performance.append((ticker, change_pct, prices[-1]))
            
            if not ticker_data:
                embed = create_embed(
                    title="📊 Stock Comparison",
                    description="No data available for the specified tickers",
                    color=discord.Color.orange()
                )
                await send_hybrid_message(ctx, embed=embed)
                return
            
            # Generate comparison chart
            chart_buffer = ChartGenerator.create_comparison_chart(ticker_data)
            
            # Create embed with performance summary
            embed = create_embed(
                title=f"📊 Stock Comparison - {days} Days",
                description=f"Comparing {len(ticker_data)} stocks",
                color=discord.Color.blue()
            )
            
            # Sort by performance
            performance.sort(key=lambda x: x[1], reverse=True)
            
            perf_text = []
            for ticker, change_pct, price in performance:
                emoji = "📈" if change_pct >= 0 else "📉"
                perf_text.append(
                    f"{emoji} **{ticker}**: {self.polygon.format_price(price)} "
                    f"({self.polygon.format_percentage(change_pct)})"
                )
            
            embed.add_field(
                name="Performance Rankings",
                value="\n".join(perf_text),
                inline=False
            )
            
            # Create file
            file = discord.File(chart_buffer, filename="comparison_chart.png")
            embed.set_image(url="attachment://comparison_chart.png")
            
            await send_hybrid_message(ctx, embed=embed, file=file)
        
        except Exception as e:
            logger.error(f"Error comparing stocks {tickers}: {e}")
            embed = create_embed(
                title="❌ Error",
                description="Could not generate comparison chart. Please try again later.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stockrsi")
    async def stock_rsi(self, ctx, ticker: str, window: int = 14):
        """Get Relative Strength Index (RSI) for a stock.
        
        RSI measures momentum on a scale of 0-100:
        - Above 70: Overbought (possible downturn)
        - Below 30: Oversold (possible upturn)
        - 50: Neutral
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
            window: RSI period (default 14 days)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            # Fetch data using service layer (returns typed models)
            current_price = await self.stock_service.get_current_price(ticker)
            rsi_indicators = await self.stock_service.get_rsi(ticker, window=window, limit=10)
            
            if not rsi_indicators:
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - RSI",
                    description="No RSI data available",
                    color=discord.Color.orange()
                )
                await send_hybrid_message(ctx, embed=embed)
                return
            
            # Get latest RSI value
            latest_rsi = rsi_indicators[0]
            
            # Analyze RSI and generate signal
            signal = IndicatorAnalyzer.analyze_rsi(latest_rsi.value, window)
            
            # Build embed using the embed builder
            embed = self.embed_builder.build_rsi_embed(
                ticker=ticker,
                current_price=current_price,
                rsi=latest_rsi,
                signal=signal,
                history=rsi_indicators[:5]
            )
            
            await send_hybrid_message(ctx, embed=embed)
        
        except Exception as e:
            logger.error(f"Error fetching RSI for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not fetch RSI for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stocksma")
    async def stock_sma(self, ctx, ticker: str, window: int = 50):
        """Get Simple Moving Average (SMA) for a stock.
        
        SMA shows the average price over a period:
        - Price above SMA: Uptrend
        - Price below SMA: Downtrend
        
        Common periods: 20 (short), 50 (medium), 200 (long)
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
            window: SMA period (default 50 days)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            # Get SMA data
            data = await self.polygon.get_sma(ticker, timespan="day", window=window, limit=10)
            results = data.get("results", {}).get("values", [])
            
            # Get current price for comparison
            price_data = await self.polygon.get_previous_close(ticker)
            current_price = price_data.get("results", [{}])[0].get("c", 0)
            
            if not results:
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - SMA",
                    description="No SMA data available",
                    color=discord.Color.orange()
                )
            else:
                latest = results[-1]
                sma_value = latest.get("value", 0)
                timestamp = latest.get("timestamp", 0)
                date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
                
                # Determine trend
                if current_price > sma_value:
                    trend = "📈 Uptrend"
                    trend_desc = f"Price (${current_price:.2f}) is above SMA - bullish signal"
                    color = discord.Color.green()
                else:
                    trend = "📉 Downtrend"
                    trend_desc = f"Price (${current_price:.2f}) is below SMA - bearish signal"
                    color = discord.Color.red()
                
                distance = ((current_price - sma_value) / sma_value * 100) if sma_value > 0 else 0
                
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - SMA ({window}-day)",
                    description=f"Simple Moving Average as of {date}",
                    color=color.value
                )
                
                embed.add_field(
                    name="Current Price",
                    value=self.polygon.format_price(current_price),
                    inline=True
                )
                
                embed.add_field(
                    name=f"SMA {window}",
                    value=self.polygon.format_price(sma_value),
                    inline=True
                )
                
                embed.add_field(
                    name="Distance",
                    value=f"{distance:+.2f}%",
                    inline=True
                )
                
                embed.add_field(
                    name="Trend Signal",
                    value=trend,
                    inline=False
                )
                
                embed.add_field(
                    name="Interpretation",
                    value=trend_desc,
                    inline=False
                )
                
                # Show recent history
                if len(results) > 1:
                    history = []
                    for r in results[-5:]:
                        sma_val = r.get("value", 0)
                        ts = r.get("timestamp", 0)
                        dt = datetime.fromtimestamp(ts / 1000).strftime("%m/%d")
                        history.append(f"{dt}: ${sma_val:.2f}")
                    
                    embed.add_field(
                        name="Recent SMA Values",
                        value="\n".join(history),
                        inline=False
                    )
        
        except Exception as e:
            logger.error(f"Error fetching SMA for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not fetch SMA for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stockema")
    async def stock_ema(self, ctx, ticker: str, window: int = 50):
        """Get Exponential Moving Average (EMA) for a stock.
        
        EMA reacts faster to price changes than SMA:
        - Price above EMA: Uptrend
        - Price below EMA: Downtrend
        
        Common periods: 12, 26 (MACD), 50 (medium), 200 (long)
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
            window: EMA period (default 50 days)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            # Get EMA data
            data = await self.polygon.get_ema(ticker, timespan="day", window=window, limit=10)
            results = data.get("results", {}).get("values", [])
            
            # Get current price
            price_data = await self.polygon.get_previous_close(ticker)
            current_price = price_data.get("results", [{}])[0].get("c", 0)
            
            if not results:
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - EMA",
                    description="No EMA data available",
                    color=discord.Color.orange()
                )
            else:
                latest = results[-1]
                ema_value = latest.get("value", 0)
                timestamp = latest.get("timestamp", 0)
                date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
                
                # Determine trend
                if current_price > ema_value:
                    trend = "📈 Uptrend"
                    trend_desc = f"Price (${current_price:.2f}) is above EMA - bullish signal"
                    color = discord.Color.green()
                else:
                    trend = "📉 Downtrend"
                    trend_desc = f"Price (${current_price:.2f}) is below EMA - bearish signal"
                    color = discord.Color.red()
                
                distance = ((current_price - ema_value) / ema_value * 100) if ema_value > 0 else 0
                
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - EMA ({window}-day)",
                    description=f"Exponential Moving Average as of {date}",
                    color=color.value
                )
                
                embed.add_field(
                    name="Current Price",
                    value=self.polygon.format_price(current_price),
                    inline=True
                )
                
                embed.add_field(
                    name=f"EMA {window}",
                    value=self.polygon.format_price(ema_value),
                    inline=True
                )
                
                embed.add_field(
                    name="Distance",
                    value=f"{distance:+.2f}%",
                    inline=True
                )
                
                embed.add_field(
                    name="Trend Signal",
                    value=trend,
                    inline=False
                )
                
                embed.add_field(
                    name="Interpretation",
                    value=trend_desc,
                    inline=False
                )
                
                # Show recent history
                if len(results) > 1:
                    history = []
                    for r in results[-5:]:
                        ema_val = r.get("value", 0)
                        ts = r.get("timestamp", 0)
                        dt = datetime.fromtimestamp(ts / 1000).strftime("%m/%d")
                        history.append(f"{dt}: ${ema_val:.2f}")
                    
                    embed.add_field(
                        name="Recent EMA Values",
                        value="\n".join(history),
                        inline=False
                    )
        
        except Exception as e:
            logger.error(f"Error fetching EMA for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not fetch EMA for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="stockmacd")
    async def stock_macd(self, ctx, ticker: str):
        """Get MACD (Moving Average Convergence Divergence) for a stock.
        
        MACD shows momentum and trend direction:
        - MACD > Signal: Bullish
        - MACD < Signal: Bearish
        - MACD crosses above Signal: Buy signal
        - MACD crosses below Signal: Sell signal
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            data = await self.polygon.get_macd(ticker, timespan="day", limit=10)
            results = data.get("results", {}).get("values", [])
            
            if not results:
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - MACD",
                    description="No MACD data available",
                    color=discord.Color.orange()
                )
            else:
                latest = results[-1]
                macd_value = latest.get("value", 0)
                signal = latest.get("signal", 0)
                histogram = latest.get("histogram", 0)
                timestamp = latest.get("timestamp", 0)
                date = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d")
                
                # Determine signal
                if macd_value > signal:
                    trend = "🟢 Bullish"
                    trend_desc = "MACD above signal line - positive momentum"
                    color = discord.Color.green()
                else:
                    trend = "🔴 Bearish"
                    trend_desc = "MACD below signal line - negative momentum"
                    color = discord.Color.red()
                
                # Check for crossover
                if len(results) > 1:
                    prev = results[-2]
                    prev_macd = prev.get("value", 0)
                    prev_signal = prev.get("signal", 0)
                    
                    if prev_macd <= prev_signal and macd_value > signal:
                        crossover = "🚀 Bullish Crossover - Strong Buy Signal"
                    elif prev_macd >= prev_signal and macd_value < signal:
                        crossover = "⚠️ Bearish Crossover - Strong Sell Signal"
                    else:
                        crossover = "No crossover"
                else:
                    crossover = "Not enough data"
                
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - MACD",
                    description=f"Moving Average Convergence Divergence as of {date}",
                    color=color.value
                )
                
                embed.add_field(
                    name="MACD Value",
                    value=f"{macd_value:.4f}",
                    inline=True
                )
                
                embed.add_field(
                    name="Signal Line",
                    value=f"{signal:.4f}",
                    inline=True
                )
                
                embed.add_field(
                    name="Histogram",
                    value=f"{histogram:.4f}",
                    inline=True
                )
                
                embed.add_field(
                    name="Current Signal",
                    value=trend,
                    inline=False
                )
                
                embed.add_field(
                    name="Interpretation",
                    value=trend_desc,
                    inline=False
                )
                
                if crossover != "Not enough data" and crossover != "No crossover":
                    embed.add_field(
                        name="⚡ Alert",
                        value=crossover,
                        inline=False
                    )
                
                # Show recent history
                if len(results) > 1:
                    history = []
                    for r in results[-5:]:
                        m_val = r.get("value", 0)
                        s_val = r.get("signal", 0)
                        ts = r.get("timestamp", 0)
                        dt = datetime.fromtimestamp(ts / 1000).strftime("%m/%d")
                        diff = m_val - s_val
                        emoji = "+" if diff > 0 else ""
                        history.append(f"{dt}: {m_val:.4f} / {s_val:.4f} ({emoji}{diff:.4f})")
                    
                    embed.add_field(
                        name="Recent MACD / Signal (Difference)",
                        value="\n".join(history),
                        inline=False
                    )
                
                embed.set_footer(text="MACD > Signal = Bullish | MACD < Signal = Bearish")
        
        except Exception as e:
            logger.error(f"Error fetching MACD for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not fetch MACD for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
        
        await send_hybrid_message(ctx, embed=embed)
    
    @commands.hybrid_command(name="goldencross")
    async def golden_cross(self, ctx, ticker: str):
        """Detect golden cross or death cross pattern.
        
        Golden Cross: 50-day SMA crosses above 200-day SMA (very bullish)
        Death Cross: 50-day SMA crosses below 200-day SMA (very bearish)
        
        This is one of the most powerful trend reversal signals in technical analysis.
        
        Args:
            ticker: Stock ticker symbol (e.g., AAPL)
        """
        if not self.polygon_enabled:
            embed = create_embed(
                title="❌ Feature Unavailable",
                description="Stock data is not configured. Please contact the bot administrator.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)
            return
        
        await defer_hybrid(ctx)
        
        try:
            # Fetch current price and both SMAs with recent history
            current_price = await self.stock_service.get_current_price(ticker)
            sma_50 = await self.stock_service.get_sma(ticker, window=50, limit=10)
            sma_200 = await self.stock_service.get_sma(ticker, window=200, limit=10)
            
            if not sma_50 or not sma_200:
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - Golden Cross",
                    description="Insufficient SMA data available. Stock may be too new or data unavailable.",
                    color=discord.Color.orange()
                )
                await send_hybrid_message(ctx, embed=embed)
                return
            
            # Need at least 2 data points to detect crossover
            if len(sma_50) < 2 or len(sma_200) < 2:
                embed = create_embed(
                    title=f"📊 {ticker.upper()} - Golden Cross",
                    description="Need more historical data to detect crossovers.",
                    color=discord.Color.orange()
                )
                await send_hybrid_message(ctx, embed=embed)
                return
            
            # Get current and previous values
            current_50 = sma_50[0].value
            current_200 = sma_200[0].value
            previous_50 = sma_50[1].value
            previous_200 = sma_200[1].value
            
            # Detect crossover
            crossover = IndicatorAnalyzer.detect_golden_cross(
                current_50, current_200,
                previous_50, previous_200
            )
            
            # Build embed based on pattern
            embed = self.embed_builder.build_golden_cross_embed(
                ticker=ticker,
                current_price=current_price,
                sma_50_current=current_50,
                sma_200_current=current_200,
                sma_50_history=sma_50[:5],
                sma_200_history=sma_200[:5],
                crossover=crossover
            )
            
            await send_hybrid_message(ctx, embed=embed)
        
        except Exception as e:
            logger.error(f"Error detecting golden cross for {ticker}: {e}")
            embed = create_embed(
                title="❌ Error",
                description=f"Could not analyze golden cross for `{ticker.upper()}`. Please try again later.",
                color=discord.Color.red()
            )
            await send_hybrid_message(ctx, embed=embed)


async def setup(bot):
    """Load the Stocks cog."""
    await bot.add_cog(Stocks(bot))
