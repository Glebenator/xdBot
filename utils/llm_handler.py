from typing import Optional, List, Dict
import aiohttp
import os
from datetime import datetime

class Message:
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

class LLMHandler:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://api-inference.huggingface.co/models/mistralai/Mistral-Nemo-Instruct-2407"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        # self.conversation_history: Dict[str, List[Message]] = {}

    def _format_prompt(self, message: str, system_prompt: Optional[str] = None) -> str:
        """Format a single message into Qwen's chat format"""
        formatted_text = ""
        if system_prompt:
            formatted_text += f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        formatted_text += f"<|im_start|>user\n{message}<|im_end|>\n"
        formatted_text += "<|im_start|>assistant\n"
        return formatted_text

    async def generate_response(self, message: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response using the LLM"""
        try:
            # Format the prompt
            formatted_text = self._format_prompt(message, system_prompt)

            # Make API request
            async with aiohttp.ClientSession() as session:
                payload = {
                    "inputs": formatted_text,
                    "parameters": {
                        "max_new_tokens": 150,
                        "temperature": 0.8,
                        "top_p": 0.95,
                        "do_sample": True,
                        "repetition_penalty": 1.1
                    }
                }
                
                async with session.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload
                ) as response:
                    response_text = await response.text()
                    
                    if response.status != 200:
                        return f"Error: API returned status {response.status}. Details: {response_text}"
                    
                    result = await response.json()
                    if isinstance(result, list) and len(result) > 0:
                        generated_text = result[0].get('generated_text', '')
                        
                        # Clean up the response by removing system message and extracting assistant response
                        parts = generated_text.split("<|im_start|>")
                        for part in parts:
                            if part.startswith("assistant\n"):
                                generated_text = part.replace("assistant\n", "").split("<|im_end|>")[0]
                                break
                        
                        return generated_text.strip()
                    
                    return f"Error: Unexpected API response format: {response_text}"
                    
        except Exception as e:
            return f"Error generating response: {str(e)}"