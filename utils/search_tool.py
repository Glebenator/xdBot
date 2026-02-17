# utils/search_tool.py
"""Tavily search tool integration for LLM function calling."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class TavilySearchTool:
    """Tavily search API wrapper for LLM tool integration."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.tavily.com",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
        include_raw_content: bool = False,
        topic: str = "general",
    ) -> Dict[str, Any]:
        """
        Execute a search query using Tavily API.

        Args:
            query: The search query string
            max_results: Maximum number of results to return (0-20)
            search_depth: 'basic' (1 credit) or 'advanced' (2 credits)
            include_answer: Include LLM-generated answer
            include_raw_content: Include raw content from results
            topic: 'general', 'news', or 'finance'

        Returns:
            Dict containing search results with 'answer', 'results', etc.
        """
        if not self.api_key:
            raise ValueError("Tavily API key is not configured")

        session = await self.get_session()
        url = f"{self.base_url}/search"

        payload = {
            "query": query,
            "max_results": min(max(0, max_results), 20),
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "topic": topic,
        }

        logger.info(
            "Tavily API Request",
            extra={
                "url": url,
                "query": query,
                "max_results": payload["max_results"],
                "search_depth": search_depth,
                "topic": topic,
            },
        )
        logger.debug(f"Tavily API Request Payload: {payload}")

        try:
            async with session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                response_status = response.status

                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "Tavily API error",
                        extra={
                            "status": response.status,
                            "url": url,
                            "query": query,
                            "error": error_text,
                        },
                    )
                    raise Exception(
                        f"Tavily API returned status {response.status}: {error_text}"
                    )

                result = await response.json()

                # Log successful response
                logger.info(
                    "Tavily API Response",
                    extra={
                        "status": response_status,
                        "query": result.get("query"),
                        "results_count": len(result.get("results", [])),
                        "has_answer": bool(result.get("answer")),
                        "response_time": result.get("response_time"),
                    },
                )
                logger.debug(f"Tavily API Raw Response: {result}")

                return result

        except aiohttp.ClientError as exc:
            logger.error(
                "Network error calling Tavily API",
                extra={"url": url, "query": query},
                exc_info=True,
            )
            raise Exception(f"Network error: {exc}") from exc

    def format_search_results(self, results: Dict[str, Any]) -> str:
        """
        Format Tavily search results into a readable string for LLM consumption.

        Args:
            results: Raw response from Tavily API

        Returns:
            Formatted string with search results
        """
        lines = []

        # Include answer if available
        if "answer" in results and results["answer"]:
            lines.append(f"Answer: {results['answer']}\n")

        # Include search results
        if "results" in results and results["results"]:
            lines.append("Search Results:")
            for i, result in enumerate(results["results"], 1):
                title = result.get("title", "No title")
                url = result.get("url", "")
                content = result.get("content", "No content")
                score = result.get("score", 0)

                lines.append(f"\n{i}. {title}")
                lines.append(f"   URL: {url}")
                lines.append(f"   Relevance: {score:.2f}")
                lines.append(f"   Content: {content}")

        return "\n".join(lines) if lines else "No results found."

    @staticmethod
    def get_tool_definition() -> Dict[str, Any]:
        """
        Get the OpenAI function/tool definition for Tavily search.

        Returns:
            Tool definition compatible with OpenAI/OpenRouter function calling
        """
        return {
            "type": "function",
            "function": {
                "name": "tavily_search",
                "description": "Search the web for current information using Tavily. Use this when you need up-to-date information, facts, news, or answers to questions you don't have knowledge about. NOTE: For stock prices, stock data, or ticker symbols, use the stock market tools instead (get_stock_price, search_stocks, get_market_status).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to execute. Be specific and clear.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of search results to return (1-10). Default is 5.",
                            "default": 5,
                        },
                        "search_depth": {
                            "type": "string",
                            "enum": ["basic", "advanced"],
                            "description": "Search depth: 'basic' for quick results, 'advanced' for more relevant and detailed results.",
                            "default": "basic",
                        },
                        "topic": {
                            "type": "string",
                            "enum": ["general", "news"],
                            "description": "Category of search: 'general' for broad searches, 'news' for current events. DO NOT use for stock/financial data - use stock tools instead.",
                            "default": "general",
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    @staticmethod
    def get_ollama_tool_definition() -> Dict[str, Any]:
        """
        Get the Ollama-compatible tool definition for Tavily search.

        Returns:
            Tool definition compatible with Ollama function calling
        """
        return {
            "type": "function",
            "function": {
                "name": "tavily_search",
                "description": "Search the web for current information. Use this when you need up-to-date information, facts, news, or answers to questions you don't have knowledge about. IMPORTANT: For stock prices, ticker symbols, or stock market data, use get_stock_price, search_stocks, or get_market_status instead.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to execute. Be specific and clear.",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of search results to return (1-10). Default is 5.",
                        },
                    },
                    "required": ["query"],
                },
            },
        }


__all__ = ["TavilySearchTool"]
