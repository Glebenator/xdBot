# utils/player_ui.py
import discord
from discord.ui import Button, View
from typing import Callable, Optional


class EffectControlView(discord.ui.View):
    """UI view for controlling audio effects"""
    def __init__(self, effect_name: str):
        super().__init__(timeout=None)
        
        # Add control buttons if the effect is adjustable
        if effect_name != 'none':
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="➖",
                custom_id=f"decrease_{effect_name}"
            ))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Reset",
                custom_id=f"reset_{effect_name}"
            ))
            self.add_item(discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="➕",
                custom_id=f"increase_{effect_name}"
            ))


class MusicControlView(View):
    """UI view for controlling music playback"""
    def __init__(self, is_live=False):
        super().__init__(timeout=None)  # Buttons won't timeout
        
        # Add buttons
        self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏸️", custom_id="pause", label="Pause"))
        self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="▶️", custom_id="resume", label="Resume"))
        self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏹️", custom_id="stop", label="Stop"))
        if not is_live:
            self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏪", custom_id="rewind", label="-10s"))
            self.add_item(Button(style=discord.ButtonStyle.secondary, emoji="⏩", custom_id="forward", label="+10s"))


class PlayerUIHelper:
    """Helper class for managing player UI elements"""
    
    @staticmethod
    def create_progress_bar(current: float, total: float, length: int = 15) -> str:
        """Create a visual progress bar using Unicode blocks"""
        percentage = current / total if total > 0 else 0
        filled_length = int(length * percentage)
        empty_length = length - filled_length
        
        bar = "▰" * filled_length + "▱" * empty_length
        return f"{bar} {int(percentage * 100)}%"

    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds into MM:SS or HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    async def send_temporary_response(interaction: discord.Interaction, content: str, delete_after: float = 5.0):
        """Send an ephemeral message that deletes itself after a specified time"""
        await interaction.response.send_message(content, ephemeral=True)
        if delete_after > 0:
            import asyncio
            await asyncio.sleep(delete_after)
            try:
                original_response = await interaction.original_response()
                await original_response.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

    @staticmethod
    async def send_chunked_message(ctx, content: str, reply_to=None) -> Optional[discord.Message]:
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
            print(f"Error in send_chunked_message: {e}")
            raise

    @staticmethod
    async def chunk_text(text: str, chunk_size: int = 1900):
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

    @staticmethod
    async def send_message_chunks(chunks, ctx=None, reply_to=None):
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