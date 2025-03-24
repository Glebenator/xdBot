# cogs/voice/button_handlers.py
"""
Handlers for button interactions in voice cogs.
"""
import discord
import logging
from typing import Optional, Dict, Any
from discord.ext import commands

from .base_cog import get_player, get_queue_manager, get_effect_manager, get_ui_helper
from utils.helpers import create_embed
from utils.audio_effects import AUDIO_EFFECTS


class ButtonHandler:
    """Base class for button interaction handlers"""
    
    @staticmethod
    async def handle_button(interaction: discord.Interaction, bot):
        """Route the button interaction to the appropriate handler"""
        custom_id = interaction.data["custom_id"]
        
        # Route to specific handlers based on button prefix
        if custom_id.startswith(("increase_", "decrease_", "reset_")):
            await EffectButtonHandler.handle_effect_button(interaction, bot)
        elif custom_id.startswith("queue_"):
            await QueueButtonHandler.handle_queue_button(interaction, bot)
        else:
            await PlaybackButtonHandler.handle_playback_button(interaction, bot)


class EffectButtonHandler:
    """Handler for audio effect buttons"""
    
    @staticmethod
    async def handle_effect_button(interaction: discord.Interaction, bot):
        """Handle effect control button interactions"""
        custom_id = interaction.data["custom_id"]
        guild_id = interaction.guild_id
        
        effect_manager = get_effect_manager()
        ui_helper = get_ui_helper()
        
        if guild_id not in effect_manager.current_effect:
            await ui_helper.send_temporary_response(interaction, "No effect currently active!", ephemeral=True)
            return

        effect_name = effect_manager.current_effect[guild_id]
        effect_config = AUDIO_EFFECTS[effect_name]
        current_intensity = effect_manager.get_effect_intensity(guild_id, effect_name)

        if custom_id.startswith("decrease"):
            new_intensity = max(
                effect_config.min_intensity,
                current_intensity - effect_config.step
            )
        elif custom_id.startswith("increase"):
            new_intensity = min(
                effect_config.max_intensity,
                current_intensity + effect_config.step
            )
        elif custom_id.startswith("reset"):
            new_intensity = effect_config.default_intensity
        else:
            await ui_helper.send_temporary_response(interaction, "Invalid button!", ephemeral=True)
            return

        # Update intensity and reapply effect
        effect_manager.set_effect_intensity(guild_id, effect_name, new_intensity)
        await effect_manager.update_effect_message(guild_id, effect_name, create_embed)
        
        # Get the context from the interaction
        ctx = await bot.get_context(interaction.message)
        
        # Get voice client
        player = get_player()
        voice_client = player.get_voice_client(interaction)
        if not voice_client:
            await ui_helper.send_temporary_response(interaction, "Not connected to a voice channel!")
            return
        
        # Get current track
        track_data = player.current_track.get(guild_id)
        if not track_data:
            await ui_helper.send_temporary_response(interaction, "No track is currently playing!")
            return
            
        # Stop current playback
        voice_client.stop()
        
        # Apply effect options
        effect_options = effect_manager.get_effect_options(
            guild_id, 
            effect_name, 
            track_data.get('start_time', 0),
            track_data.get('platform')
        )
        
        # Create new player with updated effect
        await player.create_stream_player(
            voice_client, 
            track_data,
            effect_options
        )
        
        # Acknowledge the button press
        await ui_helper.send_temporary_response(
            interaction,
            f"Effect intensity updated to {new_intensity}", 
            ephemeral=True
        )


class QueueButtonHandler:
    """Handler for queue control buttons"""
    
    @staticmethod
    async def handle_queue_button(interaction: discord.Interaction, bot):
        """Handle queue control button interactions"""
        custom_id = interaction.data["custom_id"]
        guild_id = interaction.guild_id
        
        player = get_player()
        queue_manager = get_queue_manager()
        ui_helper = get_ui_helper()
        
        voice_client = player.get_voice_client(interaction)
        if not voice_client:
            await ui_helper.send_temporary_response(interaction, "Not connected to a voice channel!")
            return
            
        # Find a reference to the queue cog to call its methods directly
        queue_cog = None
        for cog in bot.cogs.values():
            if isinstance(cog, commands.Cog) and cog.__class__.__name__ == "MusicQueue":
                queue_cog = cog
                break
                
        if custom_id == "queue_prev":
            # Play previous track
            if queue_cog:
                # Use the queue cog's method to handle previous track logic
                ctx = await bot.get_context(interaction.message)
                await queue_cog.previous_track(ctx)
                await ui_helper.send_temporary_response(
                    interaction,
                    "Playing previous track", 
                    ephemeral=True
                )
            else:
                # Fallback implementation if cog not found
                prev_track = queue_manager.get_previous_track(guild_id)
                if not prev_track:
                    await ui_helper.send_temporary_response(
                        interaction, 
                        "No previous track available!", 
                        ephemeral=True
                    )
                    return
                
                # Stop current playback
                voice_client.stop()
                
                # Play the previous track
                await player.create_stream_player(voice_client, prev_track)
                
                await ui_helper.send_temporary_response(
                    interaction,
                    f"Playing previous track: {prev_track['title']}", 
                    ephemeral=True
                )
            
        elif custom_id == "queue_next":
            # Skip to next track
            if queue_cog:
                # Use the queue cog's skip method directly
                ctx = await bot.get_context(interaction.message)
                await queue_cog.skip(ctx)
                await ui_helper.send_temporary_response(
                    interaction,
                    "Skipping to next track", 
                    ephemeral=True
                )
            else:
                # Fallback implementation
                voice_client.stop()
                await ui_helper.send_temporary_response(
                    interaction,
                    "Skipping to next track", 
                    ephemeral=True
                )
            
        elif custom_id == "queue_shuffle":
            # Shuffle the queue
            success = queue_manager.shuffle_queue(guild_id)
            if success:
                await ui_helper.send_temporary_response(
                    interaction,
                    "Queue shuffled!", 
                    ephemeral=True
                )
                
                # Update the now playing message
                for cog in bot.cogs.values():
                    if hasattr(cog, 'update_playing_message'):
                        current_track = queue_manager.get_current_track(guild_id)
                        if current_track:
                            await cog.update_playing_message(guild_id, current_track)
                        break
            else:
                await ui_helper.send_temporary_response(
                    interaction,
                    "Queue is empty or too short to shuffle!", 
                    ephemeral=True
                )
                
        elif custom_id == "queue_loop":
            # Cycle through loop modes
            current_mode = queue_manager.get_loop_mode(guild_id)
            new_mode = (current_mode + 1) % 3  # Cycle through 0, 1, 2
            
            queue_manager.set_loop_mode(guild_id, new_mode)
            
            mode_names = ["Loop disabled", "Looping current track", "Looping entire queue"]
            await ui_helper.send_temporary_response(
                interaction,
                f"{mode_names[new_mode]}", 
                ephemeral=True
            )
            
            # Update the now playing message
            for cog in bot.cogs.values():
                if hasattr(cog, 'update_playing_message'):
                    current_track = queue_manager.get_current_track(guild_id)
                    if current_track:
                        await cog.update_playing_message(guild_id, current_track)
                    break
                
        elif custom_id == "queue_clear":
            # Clear the queue
            removed = queue_manager.clear_queue(guild_id)
            await ui_helper.send_temporary_response(
                interaction,
                f"Cleared {removed} tracks from the queue!", 
                ephemeral=True
            )
            
            # Update the now playing message
            for cog in bot.cogs.values():
                if hasattr(cog, 'update_playing_message'):
                    current_track = queue_manager.get_current_track(guild_id)
                    if current_track:
                        await cog.update_playing_message(guild_id, current_track)
                    break


class PlaybackButtonHandler:
    """Handler for playback control buttons"""
    
    @staticmethod
    async def handle_playback_button(interaction: discord.Interaction, bot):
        """Handle playback control button interactions"""
        custom_id = interaction.data["custom_id"]
        guild_id = interaction.guild_id
        
        player = get_player()
        queue_manager = get_queue_manager()
        ui_helper = get_ui_helper()
        effect_manager = get_effect_manager()
        
        voice_client = player.get_voice_client(interaction)
        if not voice_client:
            await ui_helper.send_temporary_response(interaction, "Not connected to a voice channel!")
            return
            
        # Get track data from queue first, then player
        track_data = queue_manager.get_current_track(guild_id) or player.current_track.get(guild_id)
        
        if not track_data:
            await ui_helper.send_temporary_response(interaction, "No track data available!")
            return
            
        # Find a reference to the queue cog to call its methods directly
        queue_cog = None
        for cog in bot.cogs.values():
            if isinstance(cog, commands.Cog) and cog.__class__.__name__ == "MusicQueue":
                queue_cog = cog
                break
        
        try:
            if track_data.get('is_live'):
                # Handle livestream controls
                if custom_id == "pause":
                    success = await player.handle_stream_command(voice_client, track_data, "pause")
                    if success:
                        await ui_helper.send_temporary_response(interaction, "Stream paused ⏸️")
                    else:
                        await ui_helper.send_temporary_response(interaction, "Failed to pause stream")
                        
                elif custom_id == "resume":
                    success = await player.handle_stream_command(voice_client, track_data, "resume")
                    if success:
                        await ui_helper.send_temporary_response(interaction, "Stream resumed ▶️")
                    else:
                        await ui_helper.send_temporary_response(interaction, "Failed to resume stream")
                        
                elif custom_id == "stop":
                    success = await player.handle_stream_command(voice_client, track_data, "stop")
                    if success:
                        # Clean up
                        queue_manager.clear_queue(guild_id)
                        player.cleanup_for_guild(guild_id)
                        await voice_client.disconnect()
                        
                        # Delete the now playing message
                        if guild_id in player.playing_messages:
                            try:
                                await player.playing_messages[guild_id].delete()
                            except (discord.NotFound, discord.HTTPException):
                                pass
                        
                        await ui_helper.send_temporary_response(interaction, "Stream stopped and disconnected ⏹️")
                    else:
                        await ui_helper.send_temporary_response(interaction, "Failed to stop stream")
            else:
                if custom_id == "pause":
                    if voice_client.is_playing() and not voice_client.is_paused():
                        voice_client.pause()
                        await ui_helper.send_temporary_response(interaction, "Paused ⏸️")
                    else:
                        await ui_helper.send_temporary_response(interaction, "Nothing is playing!")
                        
                elif custom_id == "resume":
                    if voice_client.is_paused():
                        voice_client.resume()
                        await ui_helper.send_temporary_response(interaction, "Resumed ▶️")
                    else:
                        await ui_helper.send_temporary_response(interaction, "Not paused!")
                        
                elif custom_id == "stop":
                    if voice_client.is_playing() or voice_client.is_paused():
                        voice_client.stop()
                    
                    # Clean up
                    queue_manager.clear_queue(guild_id)
                    player.cleanup_for_guild(guild_id)
                    
                    # Disconnect from voice
                    await voice_client.disconnect()
                    
                    # Delete the now playing message
                    if guild_id in player.playing_messages:
                        try:
                            await player.playing_messages[guild_id].delete()
                        except (discord.NotFound, discord.HTTPException):
                            pass
                    
                    await ui_helper.send_temporary_response(interaction, "Stopped and left the channel ⏹️")
                        
                elif custom_id in ["forward", "rewind"]:
                    if not guild_id in player.current_track:
                        await ui_helper.send_temporary_response(interaction, "Nothing is playing!")
                        return
                        
                    track_data = player.current_track[guild_id]
                    current_time = track_data['start_time']
                    seek_time = current_time + 10 if custom_id == "forward" else current_time - 10
                    
                    seek_time = max(0, min(seek_time, track_data['duration']))
                    track_data['start_time'] = seek_time
                    
                    voice_client.stop()
                    
                    # Consider current effect when seeking
                    if guild_id in effect_manager.current_effect:
                        effect_name = effect_manager.current_effect[guild_id]
                        effect_options = effect_manager.get_effect_options(
                            guild_id, 
                            effect_name, 
                            seek_time, 
                            track_data['platform']
                        )
                        
                        await player.create_stream_player(
                            voice_client, 
                            track_data,
                            effect_options
                        )
                    else:
                        # Use platform-optimized options
                        ffmpeg_options = {
                            'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seek_time}',
                            'options': '-vn -b:a 256k -af "aresample=resampler=soxr:precision=28:dither_method=triangular_hp" -ac 2 -ar 48000'
                        }
                        
                        await player.create_stream_player(
                            voice_client, 
                            track_data,
                            ffmpeg_options
                        )
                    
                    direction = "Forward" if custom_id == "forward" else "Backward"
                    await ui_helper.send_temporary_response(
                        interaction,
                        f"{direction} 10s ({'%.1f' % seek_time}s / {track_data['duration']}s)"
                    )
        except Exception as e:
            logging.error(f"Error handling button click: {str(e)}")
            await ui_helper.send_temporary_response(
                interaction,
                f"Error handling button click: {str(e)}",
                delete_after=10.0
            )