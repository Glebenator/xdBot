"""Test chart generation without Discord."""
import asyncio
from datetime import datetime, timedelta

import config
from utils.chart_generator import ChartGenerator
from utils.polygon_handler import PolygonHandler


async def test_chart():
    """Test chart generation."""
    if not config.settings.polygon_enabled:
        print("❌ POLYGON_API_KEY not configured in .env")
        return

    polygon = PolygonHandler(config.settings.polygon_api_key)

    try:
        # Fetch data
        print("📊 Fetching AAPL data...")
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")

        data = await polygon.get_aggregates("AAPL", timespan="day", from_date=from_date, to_date=to_date)
        results = data.get("results", [])

        if not results:
            print("❌ No data returned")
            return

        print(f"✅ Got {len(results)} data points")

        # Test candlestick chart
        print("📈 Generating candlestick chart...")
        chart = ChartGenerator.create_price_chart(
            ticker="AAPL",
            data=results,
            chart_type="candlestick",
            indicators=["sma_20"]
        )

        # Save to file
        with open("test_chart.png", "wb") as f:
            f.write(chart.read())

        print("✅ Chart saved to test_chart.png")

        # Test comparison chart
        print("\n📊 Testing comparison chart...")
        msft_data = await polygon.get_aggregates("MSFT", timespan="day", from_date=from_date, to_date=to_date)

        comparison = ChartGenerator.create_comparison_chart({
            "AAPL": results,
            "MSFT": msft_data.get("results", [])
        })

        with open("test_comparison.png", "wb") as f:
            f.write(comparison.read())

        print("✅ Comparison chart saved to test_comparison.png")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await polygon.close()

if __name__ == "__main__":
    asyncio.run(test_chart())
