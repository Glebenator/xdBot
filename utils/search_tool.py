# utils/search_tool.py
"""Web search tool integration for LLM function calling.

Supports SearXNG (primary) with Tavily as fallback.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class SearXNGSearchTool:
    """SearXNG search API wrapper."""

    def __init__(
        self,
        base_url: str = "http://192.168.50.69:8888",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15)
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
        categories: str = "general",
    ) -> Dict[str, Any]:
        """
        Execute a search query using SearXNG JSON API.

        Args:
            query: The search query string
            max_results: Maximum number of results to return
            categories: Search categories (e.g. 'general', 'news')

        Returns:
            Dict containing search results normalised to the common format:
            {
                "source": "searxng",
                "results": [{"title", "url", "content", "score"}, ...],
                "answer": Optional[str],
            }
        """
        session = await self.get_session()
        url = f"{self.base_url}/search"

        params = {
            "q": query,
            "format": "json",
            "categories": categories,
        }

        logger.info(
            "SearXNG API Request",
            extra={
                "url": url,
                "query": query,
                "categories": categories,
                "max_results": max_results,
            },
        )

        try:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        "SearXNG API error",
                        extra={
                            "status": response.status,
                            "url": url,
                            "query": query,
                            "error": error_text,
                        },
                    )
                    raise Exception(
                        f"SearXNG API returned status {response.status}: {error_text}"
                    )

                raw = await response.json()

                # Normalise SearXNG response to common format
                raw_results: List[Dict[str, Any]] = raw.get("results", [])
                results: List[Dict[str, Any]] = []
                for item in raw_results[:max_results]:
                    results.append({
                        "title": item.get("title", "No title"),
                        "url": item.get("url", ""),
                        "content": item.get("content", "No content"),
                        "score": item.get("score", 0),
                    })

                # SearXNG may include an infobox or answer
                answer = None
                infoboxes = raw.get("infoboxes", [])
                if infoboxes:
                    answer = infoboxes[0].get("content", "")
                # Some SearXNG instances also provide 'answers'
                answers_list = raw.get("answers", [])
                if answers_list and not answer:
                    answer = answers_list[0] if isinstance(answers_list[0], str) else answers_list[0].get("answer", "")

                logger.info(
                    "SearXNG API Response",
                    extra={
                        "query": query,
                        "results_count": len(results),
                        "has_answer": bool(answer),
                    },
                )

                return {
                    "source": "searxng",
                    "query": query,
                    "results": results,
                    "answer": answer,
                }

        except aiohttp.ClientError as exc:
            logger.error(
                "Network error calling SearXNG API",
                extra={"url": url, "query": query},
                exc_info=True,
            )
            raise Exception(f"SearXNG network error: {exc}") from exc


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

    @staticmethod
    def get_tool_definition() -> Dict[str, Any]:
        """Get the OpenAI/OpenRouter function definition for Tavily search."""

        return WebSearchTool.get_tool_definition()

    @staticmethod
    def get_ollama_tool_definition() -> Dict[str, Any]:
        """Get the Ollama-compatible function definition for Tavily search."""

        return WebSearchTool.get_ollama_tool_definition()

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

                # Tag with source for consistency
                result["source"] = "tavily"
                return result

        except aiohttp.ClientError as exc:
            logger.error(
                "Network error calling Tavily API",
                extra={"url": url, "query": query},
                exc_info=True,
            )
            raise Exception(f"Network error: {exc}") from exc


class WebSearchTool:
    """Orchestrator: tries SearXNG first, falls back to Tavily.

    Exposes the same interface that the rest of the codebase expects
    (search, format_search_results, get_tool_definition,
    get_ollama_tool_definition).
    """

    def __init__(
        self,
        *,
        searxng_url: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
    ) -> None:
        self._searxng: Optional[SearXNGSearchTool] = None
        self._tavily: Optional[TavilySearchTool] = None

        if searxng_url:
            self._searxng = SearXNGSearchTool(base_url=searxng_url)
        if tavily_api_key:
            self._tavily = TavilySearchTool(api_key=tavily_api_key)

    async def close(self) -> None:
        """Close all underlying sessions."""
        if self._searxng:
            await self._searxng.close()
        if self._tavily:
            await self._tavily.close()

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True,
        topic: str = "general",
    ) -> Dict[str, Any]:
        """Search using SearXNG first, falling back to Tavily on failure."""

        # --- Try SearXNG first ---
        if self._searxng:
            try:
                result = await self._searxng.search(
                    query,
                    max_results=max_results,
                    categories=topic,
                )
                logger.info(
                    "Search completed via SearXNG",
                    extra={"query": query, "results_count": len(result.get("results", []))},
                )
                return result
            except Exception as exc:
                logger.warning(
                    "SearXNG search failed, falling back to Tavily",
                    extra={"query": query, "error": str(exc)},
                )

        # --- Fallback to Tavily ---
        if self._tavily:
            try:
                result = await self._tavily.search(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                    include_answer=include_answer,
                    topic=topic,
                )
                logger.info(
                    "Search completed via Tavily (fallback)",
                    extra={"query": query, "results_count": len(result.get("results", []))},
                )
                return result
            except Exception as exc:
                logger.error(
                    "Tavily fallback also failed",
                    extra={"query": query, "error": str(exc)},
                )
                raise

        raise ValueError(
            "No search backend available — neither SearXNG URL nor Tavily API key is configured"
        )

    def format_search_results(self, results: Dict[str, Any]) -> str:
        """
        Format search results into a readable string for LLM consumption.

        Args:
            results: Raw response (from either backend, normalised format)

        Returns:
            Formatted string with search results
        """
        lines = []

        source = results.get("source", "unknown")
        lines.append(f"[Search via {source}]")

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
                if score:
                    lines.append(f"   Relevance: {score:.2f}")
                lines.append(f"   Content: {content}")

        return "\n".join(lines) if lines else "No results found."

    @staticmethod
    def get_tool_definition() -> Dict[str, Any]:
        """
        Get the OpenAI function/tool definition for web search.

        Returns:
            Tool definition compatible with OpenAI/OpenRouter function calling
        """
        return {
            "type": "function",
            "function": {
                "name": "tavily_search",
                "description": "Search the web for current information. Use this when you need up-to-date information, facts, news, or answers to questions you don't have knowledge about. NOTE: For stock prices, stock data, or ticker symbols, use the stock market tools instead (get_stock_price, search_stocks, get_market_status).",
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
        Get the Ollama-compatible tool definition for web search.

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


__all__ = ["SearXNGSearchTool", "TavilySearchTool", "WebSearchTool"]
