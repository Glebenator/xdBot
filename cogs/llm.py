# cogs/llm.py
import discord
from discord.ext import commands
from utils.helpers import create_embed, defer_hybrid, send_hybrid_message
from utils.ollama_handler import LLMHandler, ModelConfig, ProviderType
from utils.db_handler import get_database_handler
from typing import Optional, List, Set, Dict
import logging
import asyncio

import config

class LLM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Initialize LLM handler with available providers
        self.llm_handler = LLMHandler(
            base_url=config.settings.ollama_url,
            openrouter_api_key=config.settings.openrouter_api_key,
            openrouter_base_url=config.settings.openrouter_base_url,
            openrouter_site_url=config.settings.openrouter_site_url,
            openrouter_app_name=config.settings.openrouter_app_name,
            tavily_api_key=config.settings.tavily_api_key,
        )
        
        self._background_tasks: Set[asyncio.Task] = set()
        self.db = get_database_handler()
        self.default_chat_model_key = 'chat'
        self.guild_chat_model_cache: Dict[int, str] = {}
        
        # Register models with specific configurations
        self.model_configs = {
            'chat': ModelConfig(
                'qwen3:4b',
                temperature=0.7,
                top_p=0.9,
                num_predict=2048,
                stop=["User:", "Assistant:"],
                max_tokens=8192,
                timeout=500  # Longer timeout for technical responses
            ),
            'mention': ModelConfig(
                'xdbot-rude',
                temperature=0.8,  # Slightly more random for personality
                top_p=0.95,
                num_predict=1024,  # Shorter responses for chat
                stop=["User:", "Assistant:"],
                max_tokens=2048,
                timeout=120,  # Shorter timeout for chat responses
                supports_tools=False  # This model doesn't support tool calling
            )
        }

        # Register models with the handler
        for key, model_cfg in self.model_configs.items():
            self.llm_handler.register_model(key, model_cfg)

        if config.settings.openrouter_default_model and config.settings.openrouter_api_key:
            openrouter_model = ModelConfig(
                config.settings.openrouter_default_model,
                provider=ProviderType.OPENROUTER,
                temperature=0.7,
                top_p=0.9,
                max_tokens=4096,
                timeout=180,
            )
            self.model_configs['chat_openrouter'] = openrouter_model
            self.llm_handler.register_model('chat_openrouter', openrouter_model)

    async def cog_unload(self):
        for task in list(self._background_tasks):
            task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()
        await self.llm_handler.close()

    def _track_task(self, task: asyncio.Task) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(self._handle_task_result)

    def _handle_task_result(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logging.error("Background task failed in LLM cog: %s", exc, exc_info=True)

    def _list_available_chat_models(self) -> List[str]:
        return [key for key in self.model_configs.keys() if key.startswith('chat')]

    def _get_model_config_for_key(self, key: str) -> ModelConfig:
        if key in self.model_configs:
            return self.model_configs[key]
        return self.model_configs[self.default_chat_model_key]

    def _format_model_summary(self, key: str) -> str:
        cfg = self._get_model_config_for_key(key)
        provider = cfg.provider.value
        return f"{key} → {cfg.model_name} ({provider})"

    async def _load_chat_model_key_from_db(self, guild_id: int) -> str:
        settings = await self.db.get_llm_settings(guild_id)
        available = set(self._list_available_chat_models())
        if settings:
            stored_key = settings.get('model_key')
            if stored_key in available:
                self.guild_chat_model_cache[guild_id] = stored_key
                return stored_key
        self.guild_chat_model_cache[guild_id] = self.default_chat_model_key
        return self.default_chat_model_key

    async def _resolve_chat_model_key(self, guild: Optional[discord.Guild]) -> str:
        if guild is None:
            return self.default_chat_model_key
        guild_id = guild.id
        cached = self.guild_chat_model_cache.get(guild_id)
        if cached in self._list_available_chat_models():
            return cached
        return await self._load_chat_model_key_from_db(guild_id)

    def format_model_response(self, content: str) -> tuple[str, Optional[str]]:
        """Format model response by separating thinking and response parts"""
        try:
            if "<think>" in content.lower() and "</think>" in content.lower():
                parts = content.split("</think>", 1)
                thinking = parts[0].replace("<think>", "").strip()
                response = parts[1].strip() if len(parts) > 1 else ""
                return response, thinking
            return content, None
        except Exception as e:
            logging.error(f"Error formatting model response: {e}")
            return content, None

    async def send_chunked_message(self, ctx, content: str, reply_to=None) -> Optional[discord.Message]:
        """Send a message in chunks if it's too long"""
        try:
            if len(content) <= 2000:
                if reply_to:
                    return await reply_to.reply(content)
                else:
                    return await ctx.send(content)

            chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
            last_message = None
            for i, chunk in enumerate(chunks):
                if i == 0 and reply_to:
                    last_message = await reply_to.reply(chunk)
                else:
                    if reply_to:
                        last_message = await reply_to.channel.send(chunk)
                    else:
                        last_message = await ctx.send(chunk)
            return last_message
        except Exception as e:
            logging.error(f"Error in send_chunked_message: {e}")
            raise

    async def chunk_text(self, text: str, chunk_size: int = 1900) -> List[str]:
        """Split text into chunks while preserving word boundaries"""
        chunks = []
        current_chunk = ""
        
        for word in text.split():
            if len(current_chunk) + len(word) + 1 > chunk_size:
                chunks.append(current_chunk.strip())
                current_chunk = word
            else:
                current_chunk += " " + word if current_chunk else word
                
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    async def send_message_chunks(self, chunks: List[str], ctx=None, reply_to=None) -> Optional[discord.Message]:
        """Send a list of chunks as sequential messages"""
        first_message = None
        
        for i, chunk in enumerate(chunks):
            content = chunk
            if i < len(chunks) - 1:
                content += " ..."
            if i > 0:
                content = "... " + content

            if i == 0:
                if reply_to:
                    first_message = await reply_to.reply(content)
                else:
                    first_message = await ctx.send(content)
            else:
                if reply_to:
                    await reply_to.channel.send(content)
                else:
                    await ctx.send(content)
                    
        return first_message

    async def send_response_with_thinking(self, ctx, response: str, thinking: Optional[str] = None, reply_to=None) -> Optional[discord.Message]:
        """Send response with optional thinking section"""
        try:
            # If no thinking, just send regular response
            if not thinking:
                return await self.send_chunked_message(ctx, response, reply_to)

            # First send the thinking part
            thinking_chunks = await self.chunk_text(thinking, 1800)  # Smaller size for formatting
            
            # Send thinking chunks
            for i, chunk in enumerate(thinking_chunks):
                content = chunk
                if i < len(thinking_chunks) - 1:
                    content += " ..."
                if i > 0:
                    content = "... " + content

                thinking_msg = f"💭 **Thinking Process:**\n```\n{content}\n```"
                
                if reply_to:
                    if i == 0:
                        await reply_to.reply(thinking_msg)
                    else:
                        await reply_to.channel.send(thinking_msg)
                else:
                    await ctx.send(thinking_msg)

            # Then send the actual response
            response_chunks = await self.chunk_text(response)
            return await self.send_message_chunks(response_chunks, ctx, reply_to)

        except Exception as e:
            logging.error(f"Error in send_response_with_thinking: {e}")
            raise

    @commands.Cog.listener()
    async def on_message(self, message):
        """Handle mentions using the rude bot model"""
        if message.author == self.bot.user:
            return

        if self.bot.user in message.mentions:
            content = message.content.replace(f'<@{self.bot.user.id}>', '').strip()
            if content:
                task = asyncio.create_task(self._handle_mention(message, content))
                self._track_task(task)

    async def _handle_mention(self, message: discord.Message, content: str) -> None:
        response_message = None
        try:
            async with message.channel.typing():
                response = await self.llm_handler.generate_response(
                    message.author.id,
                    content,
                    'mention'
                )

            if not response.is_success:
                embed = create_embed(
                    title="Error",
                    description=response.error or "An unknown error occurred.",
                    color=discord.Color.red().value
                )
                response_message = await message.reply(embed=embed)
            elif not response.content:
                embed = create_embed(
                    title="Error",
                    description="The model did not return any textual content.",
                    color=discord.Color.red().value
                )
                response_message = await message.reply(embed=embed)
            else:
                response_text, thinking = self.format_model_response(response.content or "")
                response_message = await self.send_response_with_thinking(None, response_text, thinking, reply_to=message)

        except Exception as exc:
            logging.error("Error handling mention response: %s", exc, exc_info=True)
            embed = create_embed(
                title="Error",
                description=f"An error occurred: {str(exc)}",
                color=discord.Color.red().value
            )
            if not response_message:
                await message.reply(embed=embed)

    @commands.hybrid_command(
        name="chat",
        description="Chat with the technical bot for coding and tech help"
    )
    async def chat(self, ctx, *, message: str):
        """Chat with the technical assistant model"""
        await defer_hybrid(ctx)
        response_message = None
        
        try:
            model_key = await self._resolve_chat_model_key(ctx.guild)
            model_config = self._get_model_config_for_key(model_key)
            async with ctx.typing():
                response = await self.llm_handler.generate_response(
                    ctx.author.id,
                    message,
                    model_key
                )
            
            if not response.is_success:
                embed = create_embed(
                    title="Error",
                    description=response.error or "Received empty response from the model. Please try again.",
                    color=discord.Color.red().value
                )
                response_message = await ctx.send(embed=embed)
            elif not response.content:
                embed = create_embed(
                    title="Error",
                    description="The model did not return any textual content.",
                    color=discord.Color.red().value
                )
                response_message = await ctx.send(embed=embed)
            else:
                # Split into response and thinking parts
                content = response.content or ""
                response_text, thinking = self.format_model_response(content)
                response_message = await self.send_response_with_thinking(ctx, response_text, thinking)
            
        except Exception as e:
            logging.error(f"Error in chat command: {e}")
            embed = create_embed(
                title="Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red().value
            )
            if not response_message:
                await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="clear_chat",
        description="Clear your chat history with a specific model or all models"
    )
    async def clear_chat(self, ctx, model_type: Optional[str] = None):
        """Clear the conversation history"""
        await defer_hybrid(ctx)
        message = None
        try:
            if model_type:
                if model_type not in self.model_configs:
                    await ctx.send(f"Invalid model type. Choose from: {', '.join(self.model_configs.keys())}")
                    return
                self.llm_handler.clear_history(ctx.author.id, model_type)
                description = f"Your conversation history with {model_type} model has been cleared."
            else:
                self.llm_handler.clear_history(ctx.author.id)
                description = "Your conversation history with all models has been cleared."

            embed = create_embed(
                title="Chat History Cleared",
                description=description,
                color=discord.Color.green().value
            )
            message = await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error in clear_chat: {e}")
            embed = create_embed(
                title="Error",
                description=f"Failed to clear history: {str(e)}",
                color=discord.Color.red().value
            )
            if not message:
                await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="show_history",
        description="Show your chat history with a specific model or all models"
    )
    async def show_history(self, ctx, model_type: Optional[str] = None):
        """Display the conversation history"""
        await defer_hybrid(ctx, ephemeral=True)
        message = None
        responded = False
        try:
            if model_type:
                if model_type not in self.model_configs:
                    await ctx.send(f"Invalid model type. Choose from: {', '.join(self.model_configs.keys())}")
                    return
                history = self.llm_handler.get_history(ctx.author.id, model_type)
                title = f"Chat History - {model_type.title()} Model"
            else:
                history = self.llm_handler.get_history(ctx.author.id)
                title = "Chat History - All Models"
            
            if not history:
                embed = create_embed(
                    title=title,
                    description="No chat history found.",
                    color=discord.Color.blue().value
                )
                await send_hybrid_message(ctx, embed=embed, ephemeral=True)
                responded = True
                return

            embed = create_embed(
                title=title,
                description="Here's your recent chat history:",
                color=discord.Color.blue().value
            )

            for i, msg in enumerate(history, 1):
                role = "You" if msg["role"] == "user" else "Bot"
                content = msg["content"][:1000] + "..." if len(msg["content"]) > 1000 else msg["content"]
                embed.add_field(
                    name=f"{i}. {role}",
                    value=content,
                    inline=False
                )

            await send_hybrid_message(ctx, embed=embed, ephemeral=True)
            responded = True

        except Exception as e:
            logging.error(f"Error in show_history: {e}")
            embed = create_embed(
                title="Error",
                description=f"Failed to show history: {str(e)}",
                color=discord.Color.red().value
            )
            if not responded:
                await send_hybrid_message(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="llm_set_model",
        description="Set the default chat model for this server"
    )
    @commands.has_permissions(administrator=True)
    async def llm_set_model(self, ctx, model_key: str):
        await defer_hybrid(ctx)

        if ctx.guild is None:
            embed = create_embed(
                title="Guild Only",
                description="This command can only be used inside a server.",
                color=discord.Color.red().value
            )
            await ctx.send(embed=embed)
            return

        available_keys = self._list_available_chat_models()
        if model_key not in available_keys:
            description_lines = ["Please choose one of the available chat models:"]
            for key in available_keys:
                description_lines.append(f"• {self._format_model_summary(key)}")
            embed = create_embed(
                title="Invalid Model",
                description="\n".join(description_lines),
                color=discord.Color.red().value
            )
            await ctx.send(embed=embed)
            return

        model_config = self._get_model_config_for_key(model_key)
        await self.db.set_llm_active_model(ctx.guild.id, model_key, updated_by_user_id=ctx.author.id)
        self.guild_chat_model_cache[ctx.guild.id] = model_key

        embed = create_embed(
            title="LLM Model Updated",
            description=(
                f"Default chat model set to **{model_key}**\n"
                f"Provider: `{model_config.provider.value}`\n"
                f"Model ID: `{model_config.model_name}`"
            ),
            color=discord.Color.green().value
        )
        await ctx.send(embed=embed)

    @llm_set_model.autocomplete("model_key")
    async def llm_set_model_autocomplete(self, interaction: discord.Interaction, current: str):
        current_lower = current.lower()
        choices = []
        for key in self._list_available_chat_models():
            if current_lower and current_lower not in key.lower():
                continue
            cfg = self._get_model_config_for_key(key)
            name = f"{key} ({cfg.provider.value})"
            choices.append(discord.app_commands.Choice(name=name[:100], value=key))
        return choices[:25]

    @commands.hybrid_command(
        name="llm_current_model",
        description="Show the default chat model for this server"
    )
    async def llm_current_model(self, ctx):
        await defer_hybrid(ctx, ephemeral=True)

        if ctx.guild is None:
            await send_hybrid_message(
                ctx,
                content="This command can only be used inside a server.",
                ephemeral=True
            )
            return

        model_key = await self._resolve_chat_model_key(ctx.guild)
        model_config = self._get_model_config_for_key(model_key)
        settings = await self.db.get_llm_settings(ctx.guild.id)

        embed = create_embed(
            title="Active Chat Model",
            description=(
                f"**{model_key}**\n"
                f"Provider: `{model_config.provider.value}`\n"
                f"Model ID: `{model_config.model_name}`"
            ),
            color=discord.Color.blue().value
        )

        if settings:
            if settings.get("updated_at"):
                embed.add_field(
                    name="Last Updated",
                    value=settings["updated_at"],
                    inline=False
                )
            updated_by = settings.get("updated_by_user_id")
            if updated_by:
                embed.add_field(
                    name="Updated By",
                    value=f"<@{updated_by}>",
                    inline=False
                )
        else:
            embed.set_footer(text="Using default configuration (no overrides saved).")

        available = [self._format_model_summary(key) for key in self._list_available_chat_models()]
        embed.add_field(
            name="Available Models",
            value="\n".join(available),
            inline=False
        )

        await send_hybrid_message(ctx, embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="model_stats",
        description="Show statistics for model usage"
    )
    @commands.has_permissions(administrator=True)
    async def model_stats(self, ctx, minutes: int = 60):
        """Show model usage statistics"""
        await defer_hybrid(ctx)
        try:
            metrics = self.llm_handler.get_metrics(minutes)
            
            embed = create_embed(
                title=f"Model Statistics (Last {minutes} minutes)",
                color=discord.Color.blue().value
            )
            
            embed.add_field(
                name="Total Requests",
                value=str(metrics["total_requests"]),
                inline=True
            )
            
            embed.add_field(
                name="Success Rate",
                value=f"{metrics['success_rate']:.1f}%",
                inline=True
            )
            
            embed.add_field(
                name="Average Latency",
                value=f"{metrics['average_latency']:.2f}s",
                inline=True
            )
            
            embed.add_field(
                name="Total Tokens Generated",
                value=str(metrics["total_tokens"]),
                inline=True
            )
            
            if metrics["errors"]:
                recent_errors = metrics["errors"][-5:]  # Show last 5 errors
                embed.add_field(
                    name="Recent Errors",
                    value="\n".join(recent_errors) or "None",
                    inline=False
                )

            per_model = metrics.get("per_model", {})
            if per_model:
                lines = []
                for key, stats in per_model.items():
                    provider = stats.get("provider", "?")
                    provider_model = stats.get("provider_model", "?")
                    requests = stats.get("requests", 0)
                    success_rate = stats.get("success_rate", 0.0)
                    avg_latency = stats.get("average_latency", 0.0)
                    total_tokens = stats.get("total_tokens", 0)
                    lines.append(
                        (
                            f"• **{key}** ({provider}:{provider_model}) — "
                            f"{requests} req | {success_rate:.1f}% success | "
                            f"{avg_latency:.2f}s avg | {total_tokens} tokens"
                        )
                    )
                embed.add_field(
                    name="Per Model",
                    value="\n".join(lines),
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logging.error(f"Error in model_stats: {e}")
            embed = create_embed(
                title="Error",
                description=f"Failed to get model statistics: {str(e)}",
                color=discord.Color.red().value
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LLM(bot))