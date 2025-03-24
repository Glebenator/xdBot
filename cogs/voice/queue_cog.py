# cogs/voice/queue_cog.py
"""
Queue management for music bot.
Provides commands to manage music queue.
"""
import discord
from discord.ext import commands
import logging
from typing import Optional, List

from .base_cog import BaseVoiceCog
from utils.helpers import create_embed
from utils.player_ui import QueueControlView


class MusicQueue(BaseVoiceCog):
    """Queue management for music playback"""
    
    def __init__(self, bot):
        super().__init__(bot)
    
    @commands.hybrid_command(name="queue", description="View the current music queue")
    async def view_queue(self, ctx: commands.Context):
        """View the current music queue"""
        guild_id = ctx.guild.id
        queue = self.queue_manager.get_queue(guild_id)
        
        if not queue:
            await ctx.send("The queue is empty!")
            return
        
        # Get the current index
        current_idx = self.queue_manager.current_index.get(guild_id, 0)
        
        # Create the embed
        embed = create_embed(
            title="Music Queue",
            description=f"{len(queue)} tracks in queue",
            color=discord.Color.blue().value
        )
        
        # Add loop status
        loop_mode = self.queue_manager.get_loop_mode(guild_id)
        if loop_mode == 1:
            embed.description += " | 🔂 Looping Track"
        elif loop_mode == 2:
            embed.description += " | 🔁 Looping Queue"
        
        # Add tracks to the embed (limit to 10 entries)
        display_limit = 10
        displayed_tracks = 0
        
        # Always include current track
        if 0 <= current_idx < len(queue):
            current_track = queue[current_idx]
            duration_str = "LIVE" if current_track.get('is_live') else self.ui_helper.format_time(current_track.get('duration', 0))
            embed.add_field(
                name=f"▶️ Now Playing ({duration_str})",
                value=f"{current_track['title']} [{current_track['platform']}]",
                inline=False
            )
            displayed_tracks += 1
        
        # Add next tracks
        for i in range(current_idx + 1, min(len(queue), current_idx + display_limit)):
            track = queue[i]
            duration_str = "LIVE" if track.get('is_live') else self.ui_helper.format_time(track.get('duration', 0))
            position = i - current_idx
            
            embed.add_field(
                name=f"#{position} ({duration_str})",
                value=f"{track['title']} [{track['platform']}]",
                inline=False
            )
            displayed_tracks += 1
        
        # Show how many more tracks are in the queue
        remaining = len(queue) - (current_idx + 1) - (displayed_tracks - 1)
        if remaining > 0:
            embed.set_footer(text=f"And {remaining} more track{'s' if remaining != 1 else ''}...")
        
        # Create view with queue control buttons
        view = QueueControlView()
        
        # Send the embed with queue controls
        await ctx.send(embed=embed, view=view)
    
    @commands.hybrid_command(name="add", description="Add a track to the queue")
    async def add_to_queue(self, ctx: commands.Context, *, url: str):
        """Add a track to the queue without playing it immediately"""
        try:
            # Delete the user's message if it's a text command
            if not ctx.interaction:
                try:
                    await ctx.message.delete()
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    pass
            
            await ctx.defer()
            
            # Join voice channel if not already in one
            voice_client = await self.ensure_voice_client(ctx)
            if not voice_client:
                return
            
            # Get track info
            track_info = self.player.get_track_info(url)
            
            # Add to queue
            position = self.queue_manager.add_to_queue(ctx.guild.id, track_info)
            
            # Check if this is the first track (empty queue before)
            is_first_track = position == 1
            
            # Create confirmation embed
            embed = create_embed(
                title="Added to Queue",
                description=f"🎵 {track_info['title']}" + (" 📺 LIVE" if track_info['is_live'] else ""),
                color=discord.Color.green().value
            )
            
            embed.add_field(
                name="Position",
                value=f"#{position} in queue",
                inline=True
            )
            
            if not track_info['is_live']:
                embed.add_field(
                    name="Duration",
                    value=self.ui_helper.format_time(track_info['duration']),
                    inline=True
                )
            
            if track_info.get('thumbnail'):
                embed.set_thumbnail(url=track_info['thumbnail'])
            
            await ctx.send(embed=embed)
            
            # If this is the first track, start playing it
            if is_first_track:
                # Forward to the player cog to handle initial playback
                player_cog = self.bot.get_cog('MusicPlayer')
                if player_cog:
                    await player_cog.play(ctx, url=url)  
            
        except Exception as e:
            error_embed = create_embed(
                title="Error Adding Track",
                description=str(e),
                color=discord.Color.red().value
            )
            await ctx.send(embed=error_embed)
    
    @commands.hybrid_command(name="skip", description="Skip to the next track in the queue")
    async def skip(self, ctx: commands.Context):
        """Skip to the next track in the queue"""
        voice_client = self.player.get_voice_client(ctx)
        if not voice_client:
            await ctx.send("I'm not connected to a voice channel!")
            return
        
        if not voice_client.is_playing() and not voice_client.is_paused():
            await ctx.send("Nothing is currently playing!")
            return
        
        guild_id = ctx.guild.id
        
        # Check if there's a next track
        next_track = self.queue_manager.get_next_track(guild_id)
        if next_track:
            # Stop current track (which will trigger the after function to play next)
            voice_client.stop()
            await ctx.send(f"Skipping to next track: {next_track['title']}")
        else:
            voice_client.stop()
            await ctx.send("No more tracks in queue!")
    
    @commands.hybrid_command(name="prev", description="Play the previous track in the queue")
    async def previous_track(self, ctx: commands.Context):
        """Play the previous track in the queue"""
        voice_client = self.player.get_voice_client(ctx)
        if not voice_client:
            await ctx.send("I'm not connected to a voice channel!")
            return
        
        guild_id = ctx.guild.id
        prev_track = self.queue_manager.get_previous_track(guild_id)
        
        if prev_track:
            # Stop current track
            voice_client.stop()
            
            # Update track data
            self.player.current_track[guild_id] = prev_track
            
            # Get appropriate FFmpeg options
            quality_preset = self.effect_manager.get_quality_preset(ctx.guild.id)
            ffmpeg_options = self.effect_manager.get_ffmpeg_options(
                prev_track['is_live'], 
                prev_track['platform'],
                quality_preset
            )
            
            # Apply current effect if any
            if ctx.guild.id in self.effect_manager.current_effect:
                effect_name = self.effect_manager.current_effect[ctx.guild.id]
                effect_options = self.effect_manager.get_effect_options(
                    ctx.guild.id, 
                    effect_name,
                    platform=prev_track['platform']
                )
                ffmpeg_options.update(effect_options)
            
            # Play previous track
            await self.player.create_stream_player(
                voice_client, 
                prev_track,
                ffmpeg_options
            )
            
            # Update playing message
            await self.update_playing_message(guild_id, prev_track)
            
            await ctx.send(f"Playing previous track: {prev_track['title']}")
        else:
            await ctx.send("No previous track available!")
    
    @commands.hybrid_command(name="remove", description="Remove a track from the queue by position")
    async def remove_from_queue(self, ctx: commands.Context, position: int):
        """Remove a track from the queue by position"""
        guild_id = ctx.guild.id
        queue = self.queue_manager.get_queue(guild_id)
        
        if not queue:
            await ctx.send("The queue is empty!")
            return
        
        # Adjust for 1-based user input to 0-based index
        index = position - 1
        
        # Check if position is the currently playing track
        current_idx = self.queue_manager.current_index.get(guild_id, 0)
        if index == current_idx:
            await ctx.send("Cannot remove the currently playing track. Use !skip instead.")
            return
        
        # Remove the track
        removed_track = self.queue_manager.remove_from_queue(guild_id, index)
        
        if removed_track:
            await ctx.send(f"Removed track: {removed_track['title']}")
            
            # Update playing message to reflect new queue status
            current_track = self.queue_manager.get_current_track(guild_id)
            if current_track:
                await self.update_playing_message(guild_id, current_track)
        else:
            await ctx.send(f"Invalid position: {position}")
    
    @commands.hybrid_command(name="clear", description="Clear the music queue")
    async def clear_queue(self, ctx: commands.Context):
        """Clear the music queue except for the currently playing track"""
        guild_id = ctx.guild.id
        removed = self.queue_manager.clear_queue(guild_id)
        
        if removed > 0:
            await ctx.send(f"Cleared {removed} tracks from the queue!")
            
            # Update playing message to reflect new queue status
            current_track = self.queue_manager.get_current_track(guild_id)
            if current_track:
                await self.update_playing_message(guild_id, current_track)
        else:
            await ctx.send("Queue is already empty!")
    
    @commands.hybrid_command(name="shuffle", description="Shuffle the music queue")
    async def shuffle_queue(self, ctx: commands.Context):
        """Shuffle the music queue while keeping current track"""
        guild_id = ctx.guild.id
        success = self.queue_manager.shuffle_queue(guild_id)
        
        if success:
            await ctx.send("Queue shuffled!")
            
            # Update playing message to reflect new queue status
            current_track = self.queue_manager.get_current_track(guild_id)
            if current_track:
                await self.update_playing_message(guild_id, current_track)
        else:
            await ctx.send("Queue is empty or too short to shuffle!")
    
    @commands.hybrid_command(name="loop", description="Set the loop mode (off, track, queue)")
    async def set_loop_mode(self, ctx: commands.Context, mode: str = ""):
        """
        Set the loop mode
        
        Parameters:
        -----------
        mode: str
            "off" - No looping
            "track" - Loop current track
            "queue" - Loop entire queue
            "" (empty) - Toggle through modes
        """
        guild_id = ctx.guild.id
        current_mode = self.queue_manager.get_loop_mode(guild_id)
        
        if mode.lower() == "off":
            new_mode = 0
        elif mode.lower() == "track":
            new_mode = 1
        elif mode.lower() == "queue":
            new_mode = 2
        else:
            # Toggle if no valid mode provided
            new_mode = (current_mode + 1) % 3
        
        # Set the new mode
        self.queue_manager.set_loop_mode(guild_id, new_mode)
        
        # Send confirmation
        mode_names = ["Disabled", "Current Track", "Entire Queue"]
        await ctx.send(f"Loop mode set to: **{mode_names[new_mode]}**")
        
        # Update playing message to reflect new loop status
        current_track = self.queue_manager.get_current_track(guild_id)
        if current_track:
            await self.update_playing_message(guild_id, current_track)