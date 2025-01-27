# utils/gemini_handler.py
import google.generativeai as genai
from typing import Optional, Dict, List
from datetime import datetime
from collections import deque
from utils.system_prompt import get_system_prompt

class GeminiMessage:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, str]:
        """Convert message to chat template format"""
        return {
            "role": self.role,
            "parts": [self.content]
        }

class GeminiHandler:
    def __init__(self, api_key: str, max_context_messages: int = 10):
        self.api_key = api_key
        genai.configure(api_key=api_key)
        
        # Specific configuration as provided
        self.generation_config = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }
        
        
        
        # Initialize model with specific configuration and system prompt
        self.model = genai.GenerativeModel(
            model_name="gemini-2.0-flash-thinking-exp-1219",
            generation_config=self.generation_config,
            system_instruction=get_system_prompt()
        )
        
        self.max_context_messages = max_context_messages
        self.conversation_history: Dict[int, deque[GeminiMessage]] = {}
        self.chat_sessions: Dict[int, any] = {}  # Store chat sessions per user

    def add_to_history(self, user_id: int, role: str, content: str):
        """Add a message to the conversation history"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = deque(maxlen=self.max_context_messages)
        
        self.conversation_history[user_id].append(GeminiMessage(role, content))

    def clear_history(self, user_id: int):
        """Clear conversation history for a user"""
        if user_id in self.conversation_history:
            self.conversation_history[user_id].clear()
        if user_id in self.chat_sessions:
            del self.chat_sessions[user_id]

    def get_history(self, user_id: int) -> List[Dict[str, str]]:
        """Get conversation history for a user"""
        if user_id in self.conversation_history:
            return [{"role": msg.role, "content": msg.content} for msg in self.conversation_history[user_id]]
        return []

    async def generate_response(self, user_id: int, message: str) -> str:
        """Generate a response using Gemini with conversation history"""
        try:
            # If no chat session exists for this user or if it's expired, create a new one
            if user_id not in self.chat_sessions:
                history = []
                if user_id in self.conversation_history:
                    for msg in self.conversation_history[user_id]:
                        history.append(msg.to_dict())
                
                # Add system prompt as the first message if provided
                conversation_history = []
                conversation_history.extend(history)
                
                # Start new chat session
                self.chat_sessions[user_id] = self.model.start_chat(
                    history=conversation_history
                )

            chat = self.chat_sessions[user_id]
            response = await chat.send_message_async(message)
            
            # Get only the actual response text (skip the reasoning)
            response_lines = response.text.split('\n')
            generated_text = ''
            
            # Skip lines that look like internal reasoning
            for line in response_lines:
                if not line.startswith("The user") and not line.strip().endswith("as xdBot."):
                    generated_text = line.strip()
                    break
            
            if not generated_text:
                generated_text = response_lines[-1]  # Fallback to last line if no suitable line found

            # Add the exchange to conversation history
            self.add_to_history(user_id, "user", message)
            self.add_to_history(user_id, "assistant", generated_text)

            return generated_text

        except Exception as e:
            return f"Error generating response: {str(e)}"