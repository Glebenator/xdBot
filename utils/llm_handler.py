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
        # Update to use Mixtral-8x7B-Instruct model
        self.api_url = "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def _format_prompt(self, message: str, system_prompt: Optional[str] = None) -> str:
        """Format message for Mixtral-8x7B-Instruct format"""
        # Mixtral uses a simpler instruction format
        formatted_text = ""
        if system_prompt:
            formatted_text += f"<s>[INST] System: {system_prompt}\n\n"
            formatted_text += f"User: {message} [/INST]"
        else:
            formatted_text += f"<s>[INST] {message} [/INST]"
        return formatted_text

    async def generate_response(self, message: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response using the LLM"""
        try:
            # Format the prompt for Mixtral
            formatted_text = self._format_prompt(message, system_prompt)

            # Make API request with adjusted parameters for Mixtral
            async with aiohttp.ClientSession() as session:
                payload = {
                    "inputs": formatted_text,
                    "parameters": {
                        "max_new_tokens": 150,
                        "temperature": 0.8,  # Slightly reduced for more focused responses
                        "top_p": 0.9,
                        "do_sample": True,
                        "repetition_penalty": 1.15,
                        "return_full_text": False  # Only return the generated response
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
                        
                        # Clean up the response by removing any remaining instruction tokens
                        generated_text = generated_text.replace("[/INST]", "").replace("</s>", "").strip()
                        
                        return generated_text
                    
                    return f"Error: Unexpected API response format: {str(result)}"
                    
        except Exception as e:
            return f"Error generating response: {str(e)}"