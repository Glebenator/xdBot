#!/usr/bin/env python3
"""
Demo script to show logging output for LLM and search tool operations.
Run with: python demo_logging.py
"""

import asyncio
import logging
import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

# Configure logging BEFORE importing modules
log_level = os.getenv('LLM_LOG_LEVEL', 'DEBUG').upper()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Set detailed logging for LLM and search operations
logging.getLogger('utils.ollama_handler').setLevel(getattr(logging, log_level, logging.DEBUG))
logging.getLogger('utils.search_tool').setLevel(getattr(logging, log_level, logging.DEBUG))

# Reduce noise
logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

# Now import
from utils.ollama_handler import LLMHandler, ModelConfig, ProviderType
from utils.search_tool import TavilySearchTool

logger = logging.getLogger(__name__)


async def demo_search():
    """Demonstrate search tool logging."""
    print("\n" + "="*80)
    print("DEMO: Tavily Search Tool Logging")
    print("="*80)

    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        print("⚠️  TAVILY_API_KEY not set - skipping search demo")
        return

    tool = TavilySearchTool(api_key=tavily_key)

    try:
        print("\n🔍 Executing search: 'Python programming language'")
        print("Watch the logs below for detailed request/response information:\n")

        results = await tool.search(
            query="Python programming language",
            max_results=3,
            search_depth="basic",
        )

        print("\n✅ Search completed successfully!")
        print(f"   Retrieved {len(results.get('results', []))} results")

    except Exception as e:
        print(f"\n❌ Search failed: {e}")
    finally:
        await tool.close()


async def demo_ollama_with_tools():
    """Demonstrate Ollama tool calling logging."""
    print("\n" + "="*80)
    print("DEMO: Ollama Tool Calling Logging")
    print("="*80)

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    tavily_key = os.getenv("TAVILY_API_KEY")

    if not tavily_key:
        print("⚠️  TAVILY_API_KEY not set - skipping Ollama demo")
        return

    handler = LLMHandler(
        base_url=ollama_url,
        tavily_api_key=tavily_key,
    )

    handler.register_model(
        "demo_model",
        ModelConfig(
            "llama3.1",
            provider=ProviderType.OLLAMA,
            temperature=0.7,
            timeout=60,
        )
    )

    try:
        print("\n💬 Asking LLM a question that should trigger search...")
        print("   Question: 'What is the current weather in Paris?'")
        print("Watch the logs below for the complete workflow:\n")

        response = await handler.generate_response(
            user_id=99999,
            message="What is the current weather in Paris?",
            model_key="demo_model",
            max_tool_iterations=2,
        )

        if response.error:
            print(f"\n⚠️  Response error: {response.error}")
        else:
            print("\n✅ Response generated successfully!")
            print(f"   Content preview: {response.content[:200]}...")
            if response.tool_calls:
                print(f"   Tool calls made: {len(response.tool_calls)}")

    except Exception as e:
        print(f"\n⚠️  Error (may be expected if Ollama not available): {e}")
    finally:
        await handler.close()


async def demo_openrouter_with_tools():
    """Demonstrate OpenRouter tool calling logging."""
    print("\n" + "="*80)
    print("DEMO: OpenRouter Tool Calling Logging")
    print("="*80)

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")

    if not openrouter_key:
        print("⚠️  OPENROUTER_API_KEY not set - skipping OpenRouter demo")
        return

    if not tavily_key:
        print("⚠️  TAVILY_API_KEY not set - skipping OpenRouter demo")
        return

    handler = LLMHandler(
        openrouter_api_key=openrouter_key,
        tavily_api_key=tavily_key,
    )

    handler.register_model(
        "demo_openrouter",
        ModelConfig(
            "anthropic/claude-3-haiku",
            provider=ProviderType.OPENROUTER,
            temperature=0.7,
            max_tokens=2048,
            timeout=60,
        )
    )

    try:
        print("\n💬 Asking LLM a question that should trigger search...")
        print("   Question: 'What are the latest tech news?'")
        print("Watch the logs below for the complete workflow:\n")

        response = await handler.generate_response(
            user_id=99998,
            message="What are the latest tech news?",
            model_key="demo_openrouter",
            max_tool_iterations=2,
        )

        if response.error:
            print(f"\n❌ Response error: {response.error}")
        else:
            print("\n✅ Response generated successfully!")
            print(f"   Content preview: {response.content[:200]}...")
            if response.tool_calls:
                print(f"   Tool calls made: {len(response.tool_calls)}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        await handler.close()


async def main():
    """Run all demos."""
    print("\n" + "="*80)
    print("LLM & Search Tool Logging Demo")
    print("="*80)
    print(f"\nLog Level: {os.getenv('LLM_LOG_LEVEL', 'DEBUG')}")
    print("Set LLM_LOG_LEVEL=INFO for less verbose output")
    print("Set LLM_LOG_LEVEL=DEBUG for maximum detail")

    # Demo 1: Direct search
    await demo_search()

    await asyncio.sleep(1)

    # Demo 2: Ollama with tools
    await demo_ollama_with_tools()

    await asyncio.sleep(1)

    # Demo 3: OpenRouter with tools
    await demo_openrouter_with_tools()

    print("\n" + "="*80)
    print("Demo Complete!")
    print("="*80)
    print("\nReview the logs above to see:")
    print("  • API request details")
    print("  • Tool execution workflow")
    print("  • Raw responses (in DEBUG mode)")
    print("  • Error handling")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
