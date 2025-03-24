# utils/music_queue.py
"""
Manages the music queue system for the Discord bot.
Handles track queuing, autoplay, and inactivity disconnection.
"""
import asyncio
import discord
from typing import Dict, List, Optional, Any, Callable
import logging

class QueueManager:
    """Manages music queues for multiple guilds"""
    def __init__(self, disconnect_timeout: int = 300):
        """
        Initialize the QueueManager
        
        Parameters:
        -----------
        disconnect_timeout: int
            Seconds of inactivity before the bot disconnects from voice (default: 300s / 5min)
        """
        # Maps guild_id -> list of tracks
        self.queues: Dict[int, List[Dict[str, Any]]] = {}
        # Maps guild_id -> inactivity timer
        self.inactivity_timers: Dict[int, asyncio.Task] = {}
        # Timeout in seconds
        self.disconnect_timeout = disconnect_timeout
        # Callbacks
        self._track_start_callbacks = []
        self._track_end_callbacks = []
        # Maps guild_id -> currently playing track index
        self.current_index: Dict[int, int] = {}
        # Maps guild_id -> loop mode (0=off, 1=single, 2=queue)
        self.loop_mode: Dict[int, int] = {}
        # Maps guild_id -> True if currently auto-playing next track
        self._auto_playing: Dict[int, bool] = {}
    
    def register_track_start_callback(self, callback: Callable) -> None:
        """Register a callback function to be called when a track starts playing"""
        self._track_start_callbacks.append(callback)
    
    def register_track_end_callback(self, callback: Callable) -> None:
        """Register a callback function to be called when a track ends playing"""
        self._track_end_callbacks.append(callback)
    
    async def _notify_track_start(self, guild_id: int, track: Dict[str, Any]) -> None:
        """Notify all registered callbacks that a track has started"""
        for callback in self._track_start_callbacks:
            try:
                await callback(guild_id, track)
            except Exception as e:
                logging.error(f"Error in track start callback: {e}")
    
    async def _notify_track_end(self, guild_id: int, track: Dict[str, Any]) -> None:
        """Notify all registered callbacks that a track has ended"""
        for callback in self._track_end_callbacks:
            try:
                await callback(guild_id, track)
            except Exception as e:
                logging.error(f"Error in track end callback: {e}")
    
    def get_queue(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get the queue for a guild"""
        return self.queues.get(guild_id, [])
    
    def add_to_queue(self, guild_id: int, track: Dict[str, Any]) -> int:
        """
        Add a track to the guild's queue
        
        Returns the position in the queue
        """
        if guild_id not in self.queues:
            self.queues[guild_id] = []
            self.current_index[guild_id] = 0
            self.loop_mode[guild_id] = 0  # Default: no looping
        
        # Add track to queue
        self.queues[guild_id].append(track)
        
        # Cancel inactivity timer if it's running
        self.cancel_inactivity_timer(guild_id)
        
        # Return position in queue (1-based for user display)
        return len(self.queues[guild_id])
    
    def add_multiple_to_queue(self, guild_id: int, tracks: List[Dict[str, Any]]) -> int:
        """
        Add multiple tracks to the guild's queue
        
        Returns the number of tracks added
        """
        if guild_id not in self.queues:
            self.queues[guild_id] = []
            self.current_index[guild_id] = 0
            self.loop_mode[guild_id] = 0
        
        self.queues[guild_id].extend(tracks)
        
        # Cancel inactivity timer if it's running
        self.cancel_inactivity_timer(guild_id)
        
        return len(tracks)
    
    def remove_from_queue(self, guild_id: int, position: int) -> Optional[Dict[str, Any]]:
        """
        Remove a track from the queue by position (0-based index)
        
        Returns the removed track or None if position is invalid
        """
        if guild_id not in self.queues:
            return None
        
        queue = self.queues[guild_id]
        current_idx = self.current_index.get(guild_id, 0)
        
        # Check if position is valid
        if position < 0 or position >= len(queue):
            return None
        
        # Remove track
        removed_track = queue.pop(position)
        
        # Adjust current index if needed
        if position < current_idx:
            self.current_index[guild_id] = max(0, current_idx - 1)
        elif current_idx >= len(queue):
            self.current_index[guild_id] = max(0, len(queue) - 1)
        
        return removed_track
    
    def clear_queue(self, guild_id: int) -> int:
        """
        Clear the guild's queue (except currently playing track)
        
        Returns the number of tracks removed
        """
        if guild_id not in self.queues:
            return 0
        
        current_idx = self.current_index.get(guild_id, 0)
        current_track = None
        
        # Save current track if it exists
        if 0 <= current_idx < len(self.queues[guild_id]):
            current_track = self.queues[guild_id][current_idx]
        
        # Count tracks being removed
        removed_count = len(self.queues[guild_id])
        if current_track:
            removed_count -= 1
        
        # Clear the queue
        if current_track:
            self.queues[guild_id] = [current_track]
            self.current_index[guild_id] = 0
        else:
            self.queues[guild_id] = []
            self.current_index[guild_id] = 0
        
        return removed_count
    
    def move_in_queue(self, guild_id: int, from_pos: int, to_pos: int) -> bool:
        """
        Move a track from one position to another in the queue
        
        Returns True if successful, False otherwise
        """
        if guild_id not in self.queues:
            return False
        
        queue = self.queues[guild_id]
        current_idx = self.current_index.get(guild_id, 0)
        
        # Validate positions
        if from_pos < 0 or from_pos >= len(queue) or to_pos < 0 or to_pos >= len(queue):
            return False
        
        # Don't allow moving the currently playing track
        if from_pos == current_idx:
            return False
        
        # Move the track
        track = queue.pop(from_pos)
        queue.insert(to_pos, track)
        
        # Adjust current index if needed
        if from_pos < current_idx and to_pos >= current_idx:
            self.current_index[guild_id] = current_idx - 1
        elif from_pos > current_idx and to_pos <= current_idx:
            self.current_index[guild_id] = current_idx + 1
        
        return True
    
    def shuffle_queue(self, guild_id: int) -> bool:
        """
        Shuffle the guild's queue (except currently playing track)
        
        Returns True if successful, False if queue is empty
        """
        import random
        
        if guild_id not in self.queues or len(self.queues[guild_id]) <= 1:
            return False
        
        current_idx = self.current_index.get(guild_id, 0)
        queue = self.queues[guild_id]
        
        # Save current track
        current_track = None
        if 0 <= current_idx < len(queue):
            current_track = queue[current_idx]
        
        # Create a new queue without the current track
        new_queue = [track for i, track in enumerate(queue) if i != current_idx]
        
        # Shuffle the new queue
        random.shuffle(new_queue)
        
        # Rebuild queue with current track at position 0
        if current_track:
            self.queues[guild_id] = [current_track] + new_queue
            self.current_index[guild_id] = 0
        else:
            self.queues[guild_id] = new_queue
            self.current_index[guild_id] = 0
        
        return True
    
    def get_next_track(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the next track to play based on current index and loop mode
        
        Returns the next track or None if queue is empty
        """
        if guild_id not in self.queues or not self.queues[guild_id]:
            return None
        
        queue = self.queues[guild_id]
        current_idx = self.current_index.get(guild_id, 0)
        loop_mode = self.loop_mode.get(guild_id, 0)
        
        # Handle loop modes
        if loop_mode == 1:  # Loop single track
            if 0 <= current_idx < len(queue):
                return queue[current_idx]
            else:
                # Reset if index is out of range
                self.current_index[guild_id] = 0
                return queue[0] if queue else None
        
        elif loop_mode == 2:  # Loop queue
            # Move to next track or wrap around
            next_idx = (current_idx + 1) % len(queue)
            self.current_index[guild_id] = next_idx
            return queue[next_idx]
        
        else:  # No loop
            # Move to next track if available
            next_idx = current_idx + 1
            if next_idx < len(queue):
                self.current_index[guild_id] = next_idx
                return queue[next_idx]
            else:
                return None
    
    def get_previous_track(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the previous track to play
        
        Returns the previous track or None if at the beginning
        """
        if guild_id not in self.queues or not self.queues[guild_id]:
            return None
        
        queue = self.queues[guild_id]
        current_idx = self.current_index.get(guild_id, 0)
        loop_mode = self.loop_mode.get(guild_id, 0)
        
        # Handle loop modes
        if loop_mode == 1:  # Loop single track
            if 0 <= current_idx < len(queue):
                return queue[current_idx]
            else:
                self.current_index[guild_id] = 0
                return queue[0] if queue else None
        
        elif loop_mode == 2:  # Loop queue
            # Move to previous track or wrap around
            prev_idx = (current_idx - 1) % len(queue)
            self.current_index[guild_id] = prev_idx
            return queue[prev_idx]
        
        else:  # No loop
            # Move to previous track if available
            prev_idx = current_idx - 1
            if prev_idx >= 0:
                self.current_index[guild_id] = prev_idx
                return queue[prev_idx]
            else:
                return None
    
    def get_current_track(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get the currently playing track"""
        if guild_id not in self.queues or not self.queues[guild_id]:
            return None
        
        current_idx = self.current_index.get(guild_id, 0)
        queue = self.queues[guild_id]
        
        if 0 <= current_idx < len(queue):
            return queue[current_idx]
        else:
            return None
    
    def set_loop_mode(self, guild_id: int, mode: int) -> None:
        """
        Set the loop mode for a guild
        
        mode: 0=off, 1=single track, 2=queue
        """
        if mode not in (0, 1, 2):
            raise ValueError("Loop mode must be 0 (off), 1 (single), or 2 (queue)")
        
        self.loop_mode[guild_id] = mode
    
    def get_loop_mode(self, guild_id: int) -> int:
        """Get the current loop mode for a guild"""
        return self.loop_mode.get(guild_id, 0)
    
    async def start_inactivity_timer(self, guild_id: int, voice_client: discord.VoiceClient) -> None:
        """Start the inactivity timer for a guild"""
        # Cancel existing timer if any
        self.cancel_inactivity_timer(guild_id)
        
        # Create a new timer
        self.inactivity_timers[guild_id] = asyncio.create_task(
            self._inactivity_countdown(guild_id, voice_client)
        )
    
    def cancel_inactivity_timer(self, guild_id: int) -> None:
        """Cancel the inactivity timer for a guild"""
        if guild_id in self.inactivity_timers and not self.inactivity_timers[guild_id].done():
            self.inactivity_timers[guild_id].cancel()
            self.inactivity_timers.pop(guild_id, None)
    
    async def _inactivity_countdown(self, guild_id: int, voice_client: discord.VoiceClient) -> None:
        """
        Countdown to disconnect from voice after inactivity
        
        This runs as a separate task and disconnects the bot after the timeout
        """
        try:
            await asyncio.sleep(self.disconnect_timeout)
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
                logging.info(f"Disconnected from voice in guild {guild_id} due to inactivity")
        except asyncio.CancelledError:
            # Timer was cancelled, do nothing
            pass
        except Exception as e:
            logging.error(f"Error in inactivity timer: {e}")
        finally:
            # Remove the timer
            self.inactivity_timers.pop(guild_id, None)
    
    def is_auto_playing(self, guild_id: int) -> bool:
        """Check if the guild is currently auto-playing the next track"""
        return self._auto_playing.get(guild_id, False)
    
    def set_auto_playing(self, guild_id: int, value: bool) -> None:
        """Set the auto-playing status for a guild"""
        self._auto_playing[guild_id] = value
    
    async def handle_track_finished(self, guild_id: int, voice_client: discord.VoiceClient, 
                                  player, track_data: Dict[str, Any]) -> None:
        """
        Handle when a track finishes playing
        
        This method decides what to do next (play next track or start inactivity timer)
        """
        # Notify that the track has ended
        if track_data:
            await self._notify_track_end(guild_id, track_data)
        
        # Check if another track is already auto-playing (to prevent multiple calls)
        if self.is_auto_playing(guild_id):
            return
        
        # Mark that we're handling auto-play
        self.set_auto_playing(guild_id, True)
        
        try:
            # Get the next track to play
            next_track = self.get_next_track(guild_id)
            
            if next_track:
                # Play the next track
                await player.create_stream_player(voice_client, next_track)
                await self._notify_track_start(guild_id, next_track)
            else:
                # No more tracks, start inactivity timer
                await self.start_inactivity_timer(guild_id, voice_client)
        finally:
            # Mark that we're done handling auto-play
            self.set_auto_playing(guild_id, False)