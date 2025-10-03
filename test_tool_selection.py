"""
Test script to verify tool selection prompt improvements.

This script demonstrates how the AI should select tools for different query types.
Run this after setting up the bot to verify tool selection is working correctly.
"""

# Test queries that should use STOCK tools
STOCK_QUERIES = [
    "What's the price of Apple stock?",
    "How is Tesla doing today?",
    "Is NVDA up or down?",
    "Compare Microsoft and Google stocks",
    "What's AAPL trading at?",
    "Find the ticker for Amazon",
    "Is the market open right now?",
    "Show me Apple stock price",
    "How much is one share of Tesla?",
    "What's the current stock price of NVIDIA?",
]

# Test queries that should use SEARCH tool
SEARCH_QUERIES = [
    "What happened in tech news today?",
    "Who won the Super Bowl?",
    "Latest developments in AI",
    "What's the weather in New York?",
    "Recent political events",
    "New scientific discoveries",
]

# Test queries that might use BOTH tools
MIXED_QUERIES = [
    "Tell me about Apple's new iPhone and stock price",
    "What happened to GameStop stock and why?",
    "Tesla news and current stock performance",
    "NVIDIA earnings report and stock reaction",
]

def print_test_guide():
    """Print a guide for manual testing."""
    
    print("=" * 70)
    print("STOCK MARKET TOOL SELECTION - MANUAL TEST GUIDE")
    print("=" * 70)
    print()
    
    print("📊 STOCK TOOL QUERIES (Should use get_stock_price/search_stocks/get_market_status)")
    print("-" * 70)
    for i, query in enumerate(STOCK_QUERIES, 1):
        print(f"{i:2d}. @Bot {query}")
    print()
    
    print("🔍 SEARCH TOOL QUERIES (Should use tavily_search)")
    print("-" * 70)
    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"{i:2d}. @Bot {query}")
    print()
    
    print("🔄 MIXED QUERIES (Should use BOTH tools)")
    print("-" * 70)
    for i, query in enumerate(MIXED_QUERIES, 1):
        print(f"{i:2d}. @Bot {query}")
    print()
    
    print("=" * 70)
    print("VERIFICATION STEPS:")
    print("=" * 70)
    print()
    print("1. Set debug logging in .env:")
    print("   LLM_LOG_LEVEL=DEBUG")
    print()
    print("2. Start the bot and watch the console logs")
    print()
    print("3. In Discord, mention the bot with each query above")
    print()
    print("4. Check the logs for:")
    print("   ✅ 'Executing tool call' with function_name")
    print("   ✅ Stock queries → function_name should be 'get_stock_price' or 'search_stocks'")
    print("   ✅ Search queries → function_name should be 'tavily_search'")
    print("   ❌ Stock queries using 'tavily_search' = INCORRECT")
    print()
    print("5. Verify bot responses make sense:")
    print("   ✅ Stock queries → Real-time price data with $, %, volume")
    print("   ✅ Search queries → Current web information")
    print()
    print("=" * 70)
    print("EXPECTED LOG PATTERNS:")
    print("=" * 70)
    print()
    print("For: 'What's the price of Apple stock?'")
    print("  → 'Model requested tool calls' (tool_calls_count: 1)")
    print("  → 'Executing tool call' (function_name: get_stock_price)")
    print("  → 'Stock tool execution completed'")
    print()
    print("For: 'What happened in the news today?'")
    print("  → 'Model requested tool calls' (tool_calls_count: 1)")
    print("  → 'Executing tool call' (function_name: tavily_search)")
    print("  → 'Search completed'")
    print()
    print("=" * 70)
    print()

if __name__ == "__main__":
    print_test_guide()
