# utils/ollama_handler.py
import aiohttp
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from collections import deque
import logging
import asyncio
import time
from dataclasses import dataclass

@dataclass
class RequestMetrics:
    """Class for tracking request metrics"""
    start_time: float
    end_time: float = 0.0
    tokens_generated: int = 0
    model_name: str = ""
    success: bool = False
    error: Optional[str] = None
    latency: float = 0.0

    def complete(self, success: bool, error: Optional[str] = None):
        self.end_time = time.time()
        self.success = success
        self.error = error
        self.latency = self.end_time - self.start_time

class Message:
    """Class representing a conversation message"""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, str]:
        """Convert message to chat template format"""
        return {
            "role": self.role,
            "content": self.content
        }

class ModelConfig:
    """Configuration class for different models"""
    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.temperature = kwargs.get('temperature', 0.7)
        self.top_p = kwargs.get('top_p', 0.9)
        self.num_predict = kwargs.get('num_predict', 2048)
        self.stop_sequences = kwargs.get('stop', ["User:", "Assistant:"])
        self.max_tokens = kwargs.get('max_tokens', 4096)
        self.timeout = kwargs.get('timeout', 60)

class OllamaHandler:
    def __init__(self, base_url: str = "http://ollama:11434", 
                 max_context_messages: int = 10,
                 cleanup_interval: int = 24):
        self.base_url = base_url
        self.max_context_messages = max_context_messages
        self.cleanup_interval = cleanup_interval
        self.conversation_history: Dict[int, Dict[str, deque[Message]]] = {}
        self.model_configs: Dict[str, ModelConfig] = {}
        self.metrics: List[RequestMetrics] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._last_cleanup = datetime.now()

    def register_model(self, config: ModelConfig):
        """Register a model configuration"""
        self.model_configs[config.model_name] = config

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def add_to_history(self, user_id: int, model: str, role: str, content: str):
        """Add a message to the conversation history for specific user and model"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = {}
            
        if model not in self.conversation_history[user_id]:
            self.conversation_history[user_id][model] = deque(maxlen=self.max_context_messages)
        
        self.conversation_history[user_id][model].append(Message(role, content))

    def clear_history(self, user_id: int, model: Optional[str] = None):
        """Clear conversation history for a user, optionally for specific model only"""
        if user_id in self.conversation_history:
            if model is None:
                self.conversation_history[user_id].clear()
            elif model in self.conversation_history[user_id]:
                self.conversation_history[user_id][model].clear()

    def get_history(self, user_id: int, model: Optional[str] = None) -> List[Dict[str, str]]:
        """Get conversation history for a user, optionally for specific model only"""
        if user_id not in self.conversation_history:
            return []
            
        if model is None:
            all_history = []
            for model_history in self.conversation_history[user_id].values():
                all_history.extend([msg.to_dict() for msg in model_history])
            return all_history
        
        if model in self.conversation_history[user_id]:
            return [msg.to_dict() for msg in self.conversation_history[user_id][model]]
        return []

    def cleanup_old_conversations(self):
        """Clean up old conversations based on cleanup interval"""
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

    def _format_prompt(self, user_id: int, model: str, message: str) -> str:
        """Format the prompt with conversation history for specific model"""
        prompt = ""
        
        if user_id in self.conversation_history and model in self.conversation_history[user_id]:
            for msg in self.conversation_history[user_id][model]:
                if msg.role == "user":
                    prompt += f"User: {msg.content}\n"
                else:
                    prompt += f"Assistant: {msg.content}\n"
        
        prompt += f"User: {message}\n"
        prompt += "Assistant:"
        
        return prompt

    async def generate_response(self, user_id: int, message: str, model: str) -> str:
        """Generate a response using Ollama with retry logic"""
        metrics = RequestMetrics(start_time=time.time(), model_name=model)
        max_retries = 3
        retry_delay = 1

        # Clean up old conversations periodically
        self.cleanup_old_conversations()

        # Get model config
        model_config = self.model_configs.get(model, ModelConfig(model))
        
        for attempt in range(max_retries):
            try:
                prompt = self._format_prompt(user_id, model, message)
                session = await self.get_session()
                
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": model_config.temperature,
                        "top_p": model_config.top_p,
                        "num_predict": model_config.num_predict,
                        "stop": model_config.stop_sequences
                    }
                }
                
                timeout = aiohttp.ClientTimeout(total=model_config.timeout)
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=timeout
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        error_msg = f"API returned status {response.status}. Details: {response_text}"
                        logging.error(f"Ollama API error: {error_msg}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (2 ** attempt))
                            continue
                        metrics.complete(False, error_msg)
                        self.metrics.append(metrics)
                        return f"Error: {error_msg}"
                    
                    result = await response.json()
                    if "response" in result:
                        generated_text = result["response"].strip()
                        
                        if len(generated_text) > 4000:
                            generated_text = generated_text[:4000] + "... [truncated due to length]"
                        
                        if not generated_text or generated_text.isspace():
                            error_msg = "Model returned an empty response"
                            metrics.complete(False, error_msg)
                            self.metrics.append(metrics)
                            return f"Error: {error_msg}"
                        
                        self.add_to_history(user_id, model, "user", message)
                        self.add_to_history(user_id, model, "assistant", generated_text)
                        
                        metrics.complete(True)
                        metrics.tokens_generated = len(generated_text.split())
                        self.metrics.append(metrics)
                        
                        return generated_text
                    
                    error_msg = f"Unexpected API response format: {str(result)}"
                    metrics.complete(False, error_msg)
                    self.metrics.append(metrics)
                    return f"Error: {error_msg}"
                    
            except asyncio.TimeoutError:
                error_msg = f"Request timed out after {model_config.timeout} seconds"
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                metrics.complete(False, error_msg)
                self.metrics.append(metrics)
                return f"Error: {error_msg}"
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                metrics.complete(False, error_msg)
                self.metrics.append(metrics)
                return f"Error: {error_msg}"
            
    
    def get_metrics(self, minutes: int = 60) -> Dict[str, Any]:
        """Get metrics for the last n minutes"""
        current_time = time.time()
        cutoff_time = current_time - (minutes * 60)
        
        recent_metrics = [m for m in self.metrics if m.start_time >= cutoff_time]
        
        if not recent_metrics:
            return {
                "total_requests": 0,
                "success_rate": 0,
                "average_latency": 0,
                "total_tokens": 0
            }
        
        successful_requests = [m for m in recent_metrics if m.success]
        
        return {
            "total_requests": len(recent_metrics),
            "success_rate": len(successful_requests) / len(recent_metrics) * 100,
            "average_latency": sum(m.latency for m in recent_metrics) / len(recent_metrics),
            "total_tokens": sum(m.tokens_generated for m in recent_metrics),
            "errors": [m.error for m in recent_metrics if m.error]
        }