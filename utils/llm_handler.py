# utils/llm_handler.py
from typing import Optional, List, Dict
import aiohttp
import os
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

class LLMHandler:
    def __init__(self, api_key: str, max_context_messages: int = 10):
        self.api_key = api_key
        self.api_url = "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.max_context_messages = max_context_messages
        # Store conversation history for each user
        self.conversation_history: Dict[int, deque[Message]] = {}

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

    async def generate_response(self, user_id: int, message: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response using the LLM with conversation history"""
        try:
            messages = self._format_messages(user_id, message, system_prompt)
            
            # Convert messages to Mixtral chat format
            formatted_chat = ""
            for msg in messages:
                if msg["role"] == "system":
                    formatted_chat += f"<s>[INST] System: {msg['content']}\n\n"
                elif msg["role"] == "user":
                    formatted_chat += f"User: {msg['content']}\n"
                elif msg["role"] == "assistant":
                    formatted_chat += f"Assistant: {msg['content']}\n"
            formatted_chat += "[/INST]"

            async with aiohttp.ClientSession() as session:
                payload = {
                    "inputs": formatted_chat,
                    "parameters": {
                        "max_new_tokens": 500,
                        "temperature": 0.8,
                        "top_p": 0.9,
                        "repetition_penalty": 1.15,
                        "do_sample": True,
                        "return_full_text": False
                    }
                }
                
                async with session.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        return f"Error: API returned status {response.status}. Details: {response_text}"
                    
                    result = await response.json()
                    if isinstance(result, list) and len(result) > 0:
                        generated_text = result[0].get('generated_text', '')
                        
                        # Add the exchange to conversation history
                        self.add_to_history(user_id, "user", message)
                        self.add_to_history(user_id, "assistant", generated_text)
                        
                        return generated_text
                    
                    return f"Error: Unexpected API response format: {str(result)}"
                    
        except Exception as e:
            return f"Error generating response: {str(e)}"