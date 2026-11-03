"""Integration test for chart generation without Discord."""
import asyncio
from datetime import datetime, timedelta

import pytest

import config
from utils.chart_generator import ChartGenerator
from utils.polygon_handler import PolygonHandler


@pytest.mark.integration
def test_chart():
    """Generate charts from live Polygon data when integration tests are enabled."""
    if not config.settings.polygon_enabled:
        pytest.skip("POLYGON_API_KEY is not configured")
    asyncio.run(_run_chart_test())


async def _run_chart_test() -> None:
    if not config.settings.polygon_enabled:
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
        pytest.fail(f"Chart generation failed: {e}")

    finally:
        await polygon.close()

if __name__ == "__main__":
    asyncio.run(_run_chart_test())
