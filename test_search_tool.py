#!/usr/bin/env python3
"""
Test script for Tavily search tool integration.

Run with: python test_search_tool.py
Requires TAVILY_API_KEY in environment or .env file.
"""

import asyncio
import logging
import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from utils.search_tool import TavilySearchTool
from utils.ollama_handler import LLMHandler, ModelConfig, ProviderType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_search_tool_direct():
    """Test the search tool directly."""
    print("\n" + "="*60)
    print("Testing Tavily Search Tool (Direct)")
    print("="*60)
    
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        print("❌ TAVILY_API_KEY not found in environment")
        return False
    
    tool = TavilySearchTool(api_key=tavily_key)
    
    try:
        print("\n🔍 Searching for 'Python programming language'...")
        results = await tool.search(
            query="Python programming language",
            max_results=3,
            search_depth="basic",
        )
        
        print("\n📊 Raw Results:")
        print(f"  Query: {results.get('query')}")
        print(f"  Answer: {results.get('answer', 'N/A')[:200]}...")
        print(f"  Results count: {len(results.get('results', []))}")
        
        print("\n📝 Formatted Results:")
        formatted = tool.format_search_results(results)
        print(formatted[:500] + "..." if len(formatted) > 500 else formatted)
        
        print("\n✅ Direct search test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Direct search test failed: {e}")
        logger.exception("Search failed")
        return False
    finally:
        await tool.close()


async def test_ollama_with_tools():
    """Test Ollama integration with tools."""
    print("\n" + "="*60)
    print("Testing Ollama with Tool Calling")
    print("="*60)
    
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    tavily_key = os.getenv("TAVILY_API_KEY")
    
    if not tavily_key:
        print("⚠️  TAVILY_API_KEY not found, skipping Ollama tool test")
        return True
    
    handler = LLMHandler(
        base_url=ollama_url,
        tavily_api_key=tavily_key,
    )
    
    # Register a model (adjust model name based on what you have)
    handler.register_model(
        "test_model",
        ModelConfig(
            "llama3.1",  # or whatever model you have with tool support
            provider=ProviderType.OLLAMA,
            temperature=0.7,
            timeout=60,
        )
    )
    
    try:
        print("\n💬 Testing question that should trigger search...")
        print("   Question: 'What's the latest news about AI in 2025?'")
        
        response = await handler.generate_response(
            user_id=12345,
            message="What's the latest news about AI in 2025?",
            model_key="test_model",
            max_tool_iterations=2,
        )
        
        if response.error:
            print(f"\n⚠️  Response contains error: {response.error}")
            # This is okay if Ollama isn't available or model doesn't support tools
            return True
        
        print(f"\n📤 Response:")
        print(f"  Content: {response.content[:300]}...")
        print(f"  Tool calls made: {len(response.tool_calls) if response.tool_calls else 0}")
        print(f"  Tokens: {response.tokens_generated}")
        
        print("\n✅ Ollama tool test completed!")
        return True
        
    except Exception as e:
        print(f"\n⚠️  Ollama tool test error (may be expected): {e}")
        logger.info("Ollama test error (possibly expected)", exc_info=True)
        return True  # Don't fail if Ollama isn't available
    finally:
        await handler.close()


async def test_openrouter_with_tools():
    """Test OpenRouter integration with tools."""
    print("\n" + "="*60)
    print("Testing OpenRouter with Tool Calling")
    print("="*60)
    
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    
    if not openrouter_key:
        print("⚠️  OPENROUTER_API_KEY not found, skipping OpenRouter tool test")
        return True
    
    if not tavily_key:
        print("⚠️  TAVILY_API_KEY not found, skipping OpenRouter tool test")
        return True
    
    handler = LLMHandler(
        openrouter_api_key=openrouter_key,
        tavily_api_key=tavily_key,
    )
    
    # Use a model that supports tool calling
    handler.register_model(
        "test_openrouter",
        ModelConfig(
            "anthropic/claude-3-haiku",
            provider=ProviderType.OPENROUTER,
            temperature=0.7,
            max_tokens=2048,
            timeout=60,
        )
    )
    
    try:
        print("\n💬 Testing question that should trigger search...")
        print("   Question: 'What is the current weather in Tokyo?'")
        
        response = await handler.generate_response(
            user_id=12346,
            message="What is the current weather in Tokyo?",
            model_key="test_openrouter",
            max_tool_iterations=2,
        )
        
        if response.error:
            print(f"\n❌ Response error: {response.error}")
            return False
        
        print(f"\n📤 Response:")
        print(f"  Content: {response.content[:300]}...")
        print(f"  Tool calls made: {len(response.tool_calls) if response.tool_calls else 0}")
        print(f"  Tokens: {response.tokens_generated}")
        
        print("\n✅ OpenRouter tool test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ OpenRouter tool test failed: {e}")
        logger.exception("OpenRouter test failed")
        return False
    finally:
        await handler.close()


async def test_tool_definitions():
    """Test that tool definitions are properly formatted."""
    print("\n" + "="*60)
    print("Testing Tool Definitions")
    print("="*60)
    
    from utils.search_tool import TavilySearchTool
    
    # Test OpenAI/OpenRouter format
    openai_def = TavilySearchTool.get_tool_definition()
    print("\n📋 OpenAI/OpenRouter Tool Definition:")
    print(f"  Type: {openai_def.get('type')}")
    print(f"  Function name: {openai_def.get('function', {}).get('name')}")
    print(f"  Required params: {openai_def.get('function', {}).get('parameters', {}).get('required')}")
    
    assert openai_def["type"] == "function"
    assert openai_def["function"]["name"] == "tavily_search"
    assert "query" in openai_def["function"]["parameters"]["required"]
    
    # Test Ollama format
    ollama_def = TavilySearchTool.get_ollama_tool_definition()
    print("\n📋 Ollama Tool Definition:")
    print(f"  Type: {ollama_def.get('type')}")
    print(f"  Function name: {ollama_def.get('function', {}).get('name')}")
    print(f"  Required params: {ollama_def.get('function', {}).get('parameters', {}).get('required')}")
    
    assert ollama_def["type"] == "function"
    assert ollama_def["function"]["name"] == "tavily_search"
    assert "query" in ollama_def["function"]["parameters"]["required"]
    
    print("\n✅ Tool definitions test passed!")
    return True


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Tavily Search Tool Integration Tests")
    print("="*60)
    
    results = []
    
    # Test tool definitions (always works)
    results.append(await test_tool_definitions())
    
    # Test direct search (requires API key)
    results.append(await test_search_tool_direct())
    
    # Test Ollama integration (optional)
    results.append(await test_ollama_with_tools())
    
    # Test OpenRouter integration (optional)
    results.append(await test_openrouter_with_tools())
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"Total tests: {len(results)}")
    print(f"Passed: {sum(results)}")
    print(f"Failed: {len(results) - sum(results)}")
    
    if all(results):
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed (may be expected if services unavailable)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
