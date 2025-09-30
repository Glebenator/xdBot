# utils/ollama_handler.py
from __future__ import annotations

import asyncio
import enum
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp


logger = logging.getLogger(__name__)


class ProviderType(str, enum.Enum):
    """Supported LLM provider backends."""

    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


@dataclass(slots=True)
class RequestMetrics:
    """Container for tracking request metrics"""

    start_time: float
    model_key: str
    provider_model: str
    provider: str
    end_time: float = 0.0
    tokens_generated: int = 0
    success: bool = False
    error: Optional[str] = None
    latency: float = 0.0

    def complete(self, success: bool, error: Optional[str] = None) -> None:
        self.end_time = time.time()
        self.success = success
        self.error = error
        self.latency = self.end_time - self.start_time


@dataclass(slots=True)
class Message:
    """Represents a single conversational message."""

    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": self.role}
        if self.content is not None:
            payload["content"] = self.content
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        return payload


@dataclass(slots=True)
class LLMResponse:
    """Structured response returned by providers."""

    model_key: str
    provider_model: str
    provider: ProviderType
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw: Optional[Dict[str, Any]] = None
    tokens_generated: int = 0
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None


class ModelConfig:
    """Configuration class for different models"""

    def __init__(
        self,
        model_name: str,
        provider: ProviderType | str = ProviderType.OLLAMA,
        **kwargs: Any,
    ) -> None:
        self.model_name = model_name
        self.provider = ProviderType(provider)
        self.temperature = kwargs.get("temperature", 0.7)
        self.top_p = kwargs.get("top_p", 0.9)
        self.num_predict = kwargs.get("num_predict", 2048)
        self.stop_sequences = kwargs.get("stop", ["User:", "Assistant:"])
        self.max_tokens = kwargs.get("max_tokens", 4096)
        self.timeout = kwargs.get("timeout", 60)
        self.options: Dict[str, Any] = kwargs.get("options", {})
        self.tools: Optional[List[Dict[str, Any]]] = kwargs.get("tools")
        self.tool_choice: Any = kwargs.get("tool_choice")
        self.metadata: Dict[str, Any] = kwargs.get("metadata", {})


class LLMRequestError(Exception):
    """Raised when a provider request fails."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMHandler:
    def __init__(
        self,
        base_url: str = "http://ollama:11434",
        *,
        max_context_messages: int = 10,
        cleanup_interval: int = 24,
        openrouter_api_key: Optional[str] = None,
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
        openrouter_site_url: Optional[str] = None,
        openrouter_app_name: Optional[str] = None,
        metrics_retention_minutes: int = 1440,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_context_messages = max_context_messages
        self.cleanup_interval = cleanup_interval
        self.openrouter_api_key = openrouter_api_key
        self.openrouter_base_url = openrouter_base_url.rstrip("/")
        self.openrouter_site_url = openrouter_site_url
        self.openrouter_app_name = openrouter_app_name
        self.metrics_retention_minutes = metrics_retention_minutes

        self.conversation_history: Dict[int, Dict[str, deque[Message]]] = {}
        self.model_configs: Dict[str, ModelConfig] = {}
        self.metrics: List[RequestMetrics] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._last_cleanup = datetime.now()

    def register_model(self, key: str, config: ModelConfig) -> None:
        """Register or replace a model configuration under a logical key."""

        self.model_configs[key] = config

    def list_model_keys(self) -> List[str]:
        return list(self.model_configs.keys())

    def get_model_config(self, key: str) -> Optional[ModelConfig]:
        return self.model_configs.get(key)

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""

        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=None)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""

        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def add_to_history(
        self,
        user_id: int,
        model_key: str,
        *,
        role: str,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        name: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ) -> None:
        """Add a message to the conversation history for specific user and model."""

        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = {}

        if model_key not in self.conversation_history[user_id]:
            self.conversation_history[user_id][model_key] = deque(maxlen=self.max_context_messages)

        self.conversation_history[user_id][model_key].append(
            Message(
                role=role,
                content=content,
                tool_calls=tool_calls,
                name=name,
                tool_call_id=tool_call_id,
            )
        )

    def clear_history(self, user_id: int, model_key: Optional[str] = None) -> None:
        """Clear conversation history for a user, optionally for specific model only."""

        if user_id not in self.conversation_history:
            return

        if model_key is None:
            self.conversation_history[user_id].clear()
            return

        if model_key in self.conversation_history[user_id]:
            self.conversation_history[user_id][model_key].clear()

    def get_history(self, user_id: int, model_key: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get conversation history for a user, optionally for specific model only."""

        if user_id not in self.conversation_history:
            return []

        if model_key is None:
            all_history: List[Dict[str, Any]] = []
            for history in self.conversation_history[user_id].values():
                all_history.extend(msg.to_dict() for msg in history)
            return all_history

        if model_key in self.conversation_history[user_id]:
            return [msg.to_dict() for msg in self.conversation_history[user_id][model_key]]

        return []

    def _get_history_messages(self, user_id: int, model_key: str) -> List[Message]:
        if user_id not in self.conversation_history:
            return []
        if model_key not in self.conversation_history[user_id]:
            return []
        return list(self.conversation_history[user_id][model_key])

    def cleanup_old_conversations(self) -> None:
        """Clean up old conversations based on cleanup interval."""

        current_time = datetime.now()
        if (current_time - self._last_cleanup).total_seconds() < self.cleanup_interval * 3600:
            return

        for user_id in list(self.conversation_history.keys()):
            for model in list(self.conversation_history[user_id].keys()):
                if not self.conversation_history[user_id][model]:
                    continue
                oldest_message = self.conversation_history[user_id][model][0]
                if current_time - oldest_message.timestamp > timedelta(hours=self.cleanup_interval):
                    del self.conversation_history[user_id][model]

            if not self.conversation_history[user_id]:
                del self.conversation_history[user_id]

        self._last_cleanup = current_time

    async def generate_response(
        self,
        user_id: int,
        message: str,
        model_key: str,
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = None,
    ) -> LLMResponse:
        """Generate a response using the configured provider with retry logic."""

        self.cleanup_old_conversations()

        model_config = self.model_configs.get(model_key)
        if model_config is None:
            raise LLMRequestError(f"Unknown model key: {model_key}", retryable=False)
        tools_payload = tools if tools is not None else model_config.tools
        tool_choice_payload = tool_choice if tool_choice is not None else model_config.tool_choice

        metrics = RequestMetrics(
            start_time=time.time(),
            model_key=model_key,
            provider_model=model_config.model_name,
            provider=model_config.provider.value,
        )

        max_retries = 3
        retry_delay = 1

        history_messages = self._get_history_messages(user_id, model_key)
        request_messages = [msg.to_dict() for msg in history_messages]
        request_messages.append({"role": "user", "content": message})

        for attempt in range(max_retries):
            try:
                response = await self._dispatch_request(
                    model_key,
                    model_config,
                    request_messages,
                    tools_payload,
                    tool_choice_payload,
                )

                if not response.content and not response.tool_calls:
                    raise LLMRequestError("Model returned an empty response", retryable=False)

                self.add_to_history(user_id, model_key, role="user", content=message)
                self.add_to_history(
                    user_id,
                    model_key,
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )

                metrics.tokens_generated = response.tokens_generated
                metrics.complete(True)
                self._record_metrics(metrics)
                return response

            except LLMRequestError as exc:
                logger.warning(
                    "LLM request failed",
                    extra={
                        "provider": model_config.provider.value,
                        "model": model_config.model_name,
                        "attempt": attempt + 1,
                        "retryable": exc.retryable,
                    },
                )
                if exc.retryable and attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue

                error_message = f"Error: {exc}"
                metrics.complete(False, str(exc))
                self._record_metrics(metrics)
                return LLMResponse(
                    model_key=model_key,
                    provider_model=model_config.model_name,
                    provider=model_config.provider,
                    error=error_message,
                )

            except asyncio.TimeoutError:
                error_msg = (
                    f"Request timed out after {model_config.timeout} seconds"
                )
                logger.warning(
                    "LLM request timed out",
                    extra={
                        "provider": model_config.provider.value,
                        "model": model_config.model_name,
                        "timeout": model_config.timeout,
                        "attempt": attempt + 1,
                    },
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue

                metrics.complete(False, error_msg)
                self._record_metrics(metrics)
                return LLMResponse(
                    model_key=model_key,
                    provider_model=model_config.model_name,
                    provider=model_config.provider,
                    error=f"Error: {error_msg}",
                )

            except Exception as exc:  # pragma: no cover - defensive logging
                error_msg = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "LLM request failed after retries",
                    exc_info=True,
                    extra={
                        "provider": model_config.provider.value,
                        "model": model_config.model_name,
                        "user_id": user_id,
                    },
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2**attempt))
                    continue

                metrics.complete(False, error_msg)
                self._record_metrics(metrics)
                return LLMResponse(
                    model_key=model_key,
                    provider_model=model_config.model_name,
                    provider=model_config.provider,
                    error=f"Error: {error_msg}",
                )

        # Should be unreachable but satisfies type checkers
        return LLMResponse(
            model_key=model_key,
            provider_model=model_config.model_name,
            provider=model_config.provider,
            error="Error: Unexpected provider state",
        )

    def _record_metrics(self, metrics: RequestMetrics) -> None:
        """Store metrics while trimming entries beyond the retention window."""

        cutoff = time.time() - (self.metrics_retention_minutes * 60)
        self.metrics.append(metrics)
        # Trim metrics to retention window
        if len(self.metrics) > 1:
            self.metrics = [m for m in self.metrics if m.start_time >= cutoff]

    async def _dispatch_request(
        self,
        model_key: str,
        config: ModelConfig,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
    ) -> LLMResponse:
        if config.provider is ProviderType.OLLAMA:
            return await self._generate_with_ollama(model_key, config, messages)
        if config.provider is ProviderType.OPENROUTER:
            return await self._generate_with_openrouter(model_key, config, messages, tools, tool_choice)
        raise LLMRequestError(f"Unsupported provider: {config.provider}")

    def _format_ollama_prompt(self, messages: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content") or ""
            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
            elif role == "system":
                lines.append(f"System: {content}")
            elif role == "tool":
                lines.append(f"Tool: {content}")
        lines.append("Assistant:")
        return "\n".join(lines)

    async def _generate_with_ollama(
        self,
        model_key: str,
        config: ModelConfig,
        messages: List[Dict[str, Any]],
    ) -> LLMResponse:
        prompt = self._format_ollama_prompt(messages)
        session = await self.get_session()

        payload = {
            "model": config.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "top_p": config.top_p,
                "num_predict": config.num_predict,
                "stop": config.stop_sequences,
                **config.options,
            },
        }

        timeout = aiohttp.ClientTimeout(total=config.timeout)
        async with session.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=timeout,
        ) as response:
            if response.status != 200:
                response_text = await response.text()
                retryable = response.status >= 500
                raise LLMRequestError(
                    f"API returned status {response.status}. Details: {response_text}",
                    retryable=retryable,
                )

            result = await response.json()
            generated_text = result.get("response", "")
            generated_text = (generated_text or "").strip()

            if len(generated_text) > 4000:
                generated_text = generated_text[:4000] + "... [truncated due to length]"

            tokens_generated = len(generated_text.split())

            return LLMResponse(
                model_key=model_key,
                provider_model=config.model_name,
                provider=config.provider,
                content=generated_text,
                raw=result,
                tokens_generated=tokens_generated,
            )

    async def _generate_with_openrouter(
        self,
        model_key: str,
        config: ModelConfig,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
    ) -> LLMResponse:
        if not self.openrouter_api_key:
            raise LLMRequestError(
                "OpenRouter API key is not configured", retryable=False
            )

        session = await self.get_session()
        url = f"{self.openrouter_base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_app_name:
            headers["X-Title"] = self.openrouter_app_name

        payload: Dict[str, Any] = {
            "model": config.model_name,
            "messages": messages,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_tokens,
        }

        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if config.options:
            payload.update(config.options)

        timeout = aiohttp.ClientTimeout(total=config.timeout)
        async with session.post(url, json=payload, headers=headers, timeout=timeout) as response:
            if response.status != 200:
                response_text = await response.text()
                retryable = response.status in {408, 409, 429} or response.status >= 500
                raise LLMRequestError(
                    f"API returned status {response.status}. Details: {response_text}",
                    retryable=retryable,
                )

            result = await response.json()
            choices = result.get("choices") or []
            if not choices:
                raise LLMRequestError(
                    f"Unexpected API response format: {result}", retryable=False
                )

            message_payload = choices[0].get("message") or {}
            content = (message_payload.get("content") or "").strip()
            tool_calls = message_payload.get("tool_calls")
            usage = result.get("usage") or {}
            tokens_generated = (
                usage.get("completion_tokens")
                or usage.get("total_tokens")
                or len(content.split())
            )

            if len(content) > 4000:
                content = content[:4000] + "... [truncated due to length]"

            return LLMResponse(
                model_key=model_key,
                provider_model=config.model_name,
                provider=config.provider,
                content=content,
                tool_calls=tool_calls,
                raw=result,
                tokens_generated=int(tokens_generated),
            )

    def get_metrics(self, minutes: int = 60) -> Dict[str, Any]:
        """Get aggregated metrics for the requested lookback window."""

        current_time = time.time()
        cutoff_time = current_time - (minutes * 60)
        retention_cutoff = current_time - (self.metrics_retention_minutes * 60)

        # Drop metrics older than the retention window to keep memory bounded
        if len(self.metrics) > 1 and retention_cutoff > 0:
            self.metrics = [m for m in self.metrics if m.start_time >= retention_cutoff]

        recent_metrics = [m for m in self.metrics if m.start_time >= cutoff_time]

        if not recent_metrics:
            return {
                "total_requests": 0,
                "success_rate": 0,
                "average_latency": 0,
                "total_tokens": 0,
                "errors": [],
                "per_model": {},
            }

        successful_requests = [m for m in recent_metrics if m.success]

        per_model: Dict[str, Dict[str, Any]] = {}
        for metric in recent_metrics:
            stats = per_model.setdefault(
                metric.model_key,
                {
                    "requests": 0,
                    "successes": 0,
                    "total_latency": 0.0,
                    "total_tokens": 0,
                    "provider": metric.provider,
                    "provider_model": metric.provider_model,
                },
            )
            stats["requests"] += 1
            stats["total_latency"] += metric.latency
            stats["total_tokens"] += metric.tokens_generated
            if metric.success:
                stats["successes"] += 1

        for stats in per_model.values():
            requests = max(stats["requests"], 1)
            stats["success_rate"] = (stats["successes"] / requests) * 100
            stats["average_latency"] = stats["total_latency"] / requests

        return {
            "total_requests": len(recent_metrics),
            "success_rate": len(successful_requests) / len(recent_metrics) * 100,
            "average_latency": sum(m.latency for m in recent_metrics) / len(recent_metrics),
            "total_tokens": sum(m.tokens_generated for m in recent_metrics),
            "errors": [m.error for m in recent_metrics if m.error],
            "per_model": per_model,
        }


# Backwards compatibility export
OllamaHandler = LLMHandler

__all__ = [
    "LLMHandler",
    "OllamaHandler",
    "ModelConfig",
    "LLMResponse",
    "ProviderType",
]