import aiohttp
from typing import Optional, Dict, List
from datetime import datetime
from collections import deque

class Message:
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

class OllamaHandler:
    def __init__(self, base_url: str = "http://ollama:11434", max_context_messages: int = 10):
        self.base_url = base_url
        self.max_context_messages = max_context_messages
        self.conversation_history: Dict[int, deque[Message]] = {}

    def add_to_history(self, user_id: int, role: str, content: str):
        """Add a message to the conversation history"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = deque(maxlen=self.max_context_messages)
        
        self.conversation_history[user_id].append(Message(role, content))

    def clear_history(self, user_id: int):
        """Clear conversation history for a user"""
        if user_id in self.conversation_history:
            self.conversation_history[user_id].clear()

    def get_history(self, user_id: int) -> List[Dict[str, str]]:
        """Get conversation history for a user"""
        if user_id in self.conversation_history:
            return [msg.to_dict() for msg in self.conversation_history[user_id]]
        return []

    def _format_messages(self, user_id: int, message: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """Format messages for the chat template"""
        messages = []
        
        # Add system message if provided
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history
        if user_id in self.conversation_history:
            messages.extend(msg.to_dict() for msg in self.conversation_history[user_id])
        
        # Add current message
        messages.append({"role": "user", "content": message})
        return messages

    async def generate_response(self, user_id: int, message: str, model: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response using Ollama"""
        try:
            messages = self._format_messages(user_id, message, system_prompt)
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                }
                
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        return f"Error: API returned status {response.status}. Details: {response_text}"
                    
                    result = await response.json()
                    if "message" in result:
                        generated_text = result["message"]["content"]
                        
                        # Add the exchange to conversation history
                        self.add_to_history(user_id, "user", message)
                        self.add_to_history(user_id, "assistant", generated_text)
                        
                        return generated_text
                    
                    return f"Error: Unexpected API response format: {str(result)}"
                    
        except Exception as e:
            return f"Error generating response: {str(e)}"