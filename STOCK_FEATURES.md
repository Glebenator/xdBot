# Stock Market Features - Complete Documentation

## Overview
This bot integrates with Polygon.io API to provide comprehensive stock market data, technical analysis, and visual charts through Discord commands and AI-powered tools.

**API:** Polygon.io (Free Tier)  
**Features:** 13 commands + 7 AI tools  
**Chart Generation:** matplotlib with candlestick, line, and area charts

---

## Quick Start

### Setup
1. Get free API key from [polygon.io](https://polygon.io/dashboard/signup)
2. Add to `.env`: `POLYGON_API_KEY=your_key_here`
3. Install dependencies: `pip install -r requirements.txt`
4. Restart bot

### Basic Commands
```bash
!stock AAPL                    # Current price
!stockchart AAPL               # Visual chart
!stockrsi AAPL                 # Technical indicator
```

---

## All Commands (13 Total)

### Price & Information (4 commands)

#### `!stock <ticker>`
Get current stock price and trading data.
```bash
!stock AAPL
```
**Shows:** Price, change %, volume, open/high/low

#### `!stockinfo <ticker>`
Get detailed company information.
```bash
!stockinfo MSFT
```
**Shows:** Company name, description, market cap, website

#### `!stocksearch <query>`
Search for ticker symbols by company name.
```bash
!stocksearch apple
```
**Shows:** Matching tickers with company names

#### `!marketstatus`
Check if stock market is open.
```bash
!marketstatus
```
**Shows:** NYSE, NASDAQ, OTC status

---

### News & Events (3 commands)

#### `!stocknews <ticker> [count]`
Get latest news articles.
```bash
!stocknews AAPL 5
```
**Shows:** Headlines, dates, links

#### `!stockdividends <ticker>`
View dividend payment history.
```bash
!stockdividends AAPL
```
**Shows:** Payment dates, amounts

#### `!stocksplits <ticker>`
View stock split history.
```bash
!stocksplits TSLA
```
**Shows:** Split ratios, dates

---

### Charts (2 commands)

#### `!stockchart <ticker> [days] [type] [indicators]`
Generate visual price charts with technical indicators.

**Chart Types:**
- `candlestick` (default) - OHLC bars
- `line` - Simple line chart
- `area` - Filled area chart

**Indicators:**
- `sma_X` - Simple Moving Average (e.g., sma_20, sma_50, sma_200)
- `ema_X` - Exponential Moving Average (e.g., ema_12, ema_26)

**Examples:**
```bash
!stockchart AAPL                              # 30-day candlestick
!stockchart TSLA 90 line                      # 90-day line chart
!stockchart MSFT 60 area sma_20,sma_50       # Area + MAs
!stockchart GOOGL 30 candlestick ema_12,ema_26  # EMAs
```

**Features:**
- Professional PNG charts (150 DPI)
- Discord dark theme styling
- Volume bars below price
- Price change overlay
- Multiple indicator support

#### `!stockcompare <tickers> [days]`
Compare performance of multiple stocks.
```bash
!stockcompare AAPL,MSFT,GOOGL
!stockcompare NVDA,AMD,INTC 90
```
**Features:**
- Normalized % change chart
- Performance rankings
- Up to 5 stocks

---

### Technical Indicators (4 commands)

#### `!stockrsi <ticker> [window]`
Relative Strength Index - overbought/oversold detector.

**RSI Scale:**
- **>70** = Overbought (potential sell)
- **<30** = Oversold (potential buy)
- **~50** = Neutral

**Examples:**
```bash
!stockrsi AAPL              # 14-day RSI (default)
!stockrsi TSLA 9            # 9-day RSI (faster)
```

**Shows:** RSI value, signal (🟢🟡🔴), interpretation, 5-day history

#### `!stocksma <ticker> [window]`
Simple Moving Average - trend identification.

**Common Periods:**
- 20 days = short-term
- 50 days = medium-term (default)
- 200 days = long-term

**Examples:**
```bash
!stocksma AAPL              # 50-day SMA
!stocksma MSFT 200          # 200-day SMA
```

**Shows:** Current price vs SMA, distance %, trend signal (📈📉)

#### `!stockema <ticker> [window]`
Exponential Moving Average - faster trend detection.

**Examples:**
```bash
!stockema AAPL              # 50-day EMA
!stockema NVDA 12           # 12-day EMA (fast)
```

**Shows:** Current price vs EMA, distance %, trend signal

#### `!stockmacd <ticker>`
MACD - momentum and buy/sell signals.

**Examples:**
```bash
!stockmacd AAPL
!stockmacd TSLA
```

**Shows:** MACD value, signal line, histogram, crossover alerts (🚀⚠️)

---

## AI Integration (7 Tools)

The LLM can automatically use these tools when you ask questions:

### Stock Price Tools
- `get_stock_price(ticker)` - Get current price
- `search_stocks(query)` - Find ticker symbols
- `get_market_status()` - Check market hours

### Technical Indicator Tools
- `get_stock_rsi(ticker, window)` - RSI indicator
- `get_stock_sma(ticker, window)` - SMA indicator
- `get_stock_ema(ticker, window)` - EMA indicator
- `get_stock_macd(ticker)` - MACD indicator

### Example AI Queries
```
"What's the price of Apple stock?"        → Uses get_stock_price
"Is Tesla overbought?"                    → Uses get_stock_rsi
"What's the 50-day MA for Microsoft?"    → Uses get_stock_sma
"Show me MACD for NVDA"                   → Uses get_stock_macd
"Is the market open?"                     → Uses get_market_status
```

---

## Trading Workflows

### Day Trading
```bash
!stockrsi AAPL 9            # Check if oversold (entry)
!stockmacd AAPL             # Confirm momentum
!stockchart AAPL 5 candlestick ema_12
```

### Swing Trading
```bash
!stocksma TSLA 50           # Medium-term trend
!stockrsi TSLA              # Not overbought?
!stockchart TSLA 30 candlestick sma_20,sma_50
```

### Long-Term Investing
```bash
!stocksma SPY 200           # Long-term trend
!stockinfo SPY              # Fundamentals
!stockchart SPY 365 line sma_200
```

### Golden Cross Detection
```bash
!stocksma DIA 50
!stocksma DIA 200
!stockchart DIA 250 candlestick sma_50,sma_200
```

---

## Technical Details

### Free Tier Limitations
- ✅ End-of-day data (no real-time)
- ✅ 5 API calls per minute
- ✅ Max 365 days history
- ✅ Basic aggregates & indicators
- ❌ No intraday data
- ❌ No snapshot endpoint (requires paid plan)

### Chart Generation
- **Library:** matplotlib 3.8.0+
- **Resolution:** 150 DPI
- **File Size:** 200-400KB per chart
- **Generation Time:** 1-3 seconds
- **Theme:** Discord dark (#2b2d31 background)
- **Colors:** Green (up), Red (down), Blue (indicators)

### File Structure
```
utils/
  polygon_handler.py    # API wrapper (14+ methods)
  stock_tool.py         # LLM tool integration (7 tools)
  chart_generator.py    # Chart creation (matplotlib)
cogs/
  stocks.py            # Discord commands (13 commands)
```

---

## Common Use Cases

### Quick Price Check
```bash
!stock AAPL
```

### Trend Analysis
```bash
!stockchart AAPL 90 candlestick sma_50,sma_200
```

### Momentum Check
```bash
!stockrsi AAPL
!stockmacd AAPL
```

### Sector Comparison
```bash
!stockcompare XLK,XLF,XLE,XLV,XLI 90
```

### News Research
```bash
!stocknews TSLA 5
!stockdividends AAPL
```

---

## Troubleshooting

### "Stock data is not configured"
- Set `POLYGON_API_KEY` in `.env`
- Restart bot

### "No data available"
- Verify ticker symbol: `!stocksearch apple`
- Check if market was open during period

### Rate Limit Errors
- Free tier: 5 calls/minute
- Wait 1 minute between heavy usage

### 403 Forbidden
- Endpoint not available on free tier
- Check [pricing](https://polygon.io/pricing)

---

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `!stock` | Current price | `!stock AAPL` |
| `!stockchart` | Visual chart | `!stockchart AAPL 30 candlestick sma_20` |
| `!stockrsi` | RSI indicator | `!stockrsi AAPL` |
| `!stocksma` | Moving average | `!stocksma AAPL 50` |
| `!stockmacd` | MACD momentum | `!stockmacd AAPL` |
| `!stockcompare` | Compare stocks | `!stockcompare AAPL,MSFT,GOOGL` |
| `!stocknews` | Latest news | `!stocknews AAPL 5` |

---

## Resources

- [Polygon.io Dashboard](https://polygon.io/dashboard)
- [API Documentation](https://polygon.io/docs/rest/quickstart)
- [Supported Tickers](https://polygon.io/docs/rest/reference/tickers)
- [API Status](https://status.polygon.io/)

---

## Technical Indicator Reference

### RSI (Relative Strength Index)
- **Range:** 0-100
- **Overbought:** >70
- **Oversold:** <30
- **Use:** Entry/exit timing

### SMA (Simple Moving Average)
- **Popular periods:** 20, 50, 200 days
- **Price > SMA:** Uptrend (bullish)
- **Price < SMA:** Downtrend (bearish)
- **Use:** Trend identification

### EMA (Exponential Moving Average)
- **Popular periods:** 12, 26, 50, 200 days
- **Reacts faster** than SMA
- **MACD components:** EMA 12 & 26
- **Use:** Short-term trends

### MACD
- **MACD > Signal:** Bullish
- **MACD < Signal:** Bearish
- **Crossovers:** Strong buy/sell signals
- **Use:** Momentum and timing

---

## Implementation Summary

### Files Created/Modified

**New Files:**
- `utils/chart_generator.py` - Chart generation (373 lines)
- `utils/stock_tool.py` - LLM tools (860 lines)
- `utils/polygon_handler.py` - API wrapper (435 lines)

**Modified Files:**
- `cogs/stocks.py` - 13 commands (1300+ lines)
- `utils/ollama_handler.py` - Tool integration updates
- `config.py` - Polygon API settings
- `requirements.txt` - Added matplotlib

**Total:** ~3000 lines of code

### Dependencies Added
```
matplotlib>=3.8.0
aiohttp>=3.9.1  (already included)
```

---

## What's Next?

### Future Enhancements (Optional)
- More indicators (Bollinger Bands, Stochastic)
- Pattern recognition (head & shoulders, triangles)
- Price alerts and notifications
- Portfolio tracking
- Screening tools (find stocks with RSI < 30)
- Custom themes for charts
- Interactive web-based charts

---

**Last Updated:** October 2, 2025  
**Version:** 2.0  
**Status:** Production Ready ✅
