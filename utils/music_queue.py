"""Music queue management for multi-guild playback.

This module provides data structures and management for per-guild music
queues, ensuring thread-safe operations and clean state management.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Dict, Optional

import discord

from utils.music_exceptions import QueueEmptyError, QueueFullError
from config import settings

logger = logging.getLogger(__name__)


class LoopMode(Enum):
    """Loop mode for queue playback."""
    OFF = 0
    SONG = 1
    QUEUE = 2


@dataclass
class Song:
    """Represents a song in the queue.
    
    Attributes:
        title: Song title
        url: Direct audio stream URL
        webpage_url: Original webpage URL
        duration: Duration in seconds
        thumbnail: Thumbnail image URL
        requester: Discord member who requested the song
        uploader: Original uploader/channel name
    """
    title: str
    url: str
    webpage_url: str
    duration: int
    thumbnail: Optional[str]
    requester: discord.Member
    uploader: Optional[str] = None
    http_headers: Optional[Dict[str, str]] = None
    
    def __str__(self) -> str:
        """String representation showing title and requester."""
        return f"{self.title} (requested by {self.requester.display_name})"
    
    @property
    def formatted_duration(self) -> str:
        """Get formatted duration string."""
        if self.duration <= 0:
            return "Unknown"
        
        hours, remainder = divmod(self.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


class GuildMusicQueue:
    """Manages music queue for a single guild.
    
    This class handles queue operations, loop modes, and current playback
    state for a specific Discord guild.
    """
    
    def __init__(self, guild_id: int, max_size: int = 100, default_volume: float = 0.5):
        """Initialize guild music queue.
        
        Args:
            guild_id: Discord guild ID
            max_size: Maximum queue size
        """
        self.guild_id = guild_id
        self.max_size = max_size
        self._queue: Deque[Song] = deque(maxlen=max_size)
        self._current: Optional[Song] = None
        self._loop_mode: LoopMode = LoopMode.OFF
        self._volume: float = max(0.0, min(1.0, default_volume))
        self._lock = asyncio.Lock()
        
        logger.debug(f"Initialized music queue for guild {guild_id}")
    
    @property
    def current(self) -> Optional[Song]:
        """Get currently playing song."""
        return self._current
    
    @property
    def loop_mode(self) -> LoopMode:
        """Get current loop mode."""
        return self._loop_mode
    
    @property
    def volume(self) -> float:
        """Get current volume (0.0 to 1.0)."""
        return self._volume
    
    @volume.setter
    def volume(self, value: float):
        """Set volume (0.0 to 1.0)."""
        self._volume = max(0.0, min(1.0, value))
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._queue) == 0
    
    def is_full(self) -> bool:
        """Check if queue is at maximum capacity."""
        return len(self._queue) >= self.max_size
    
    def __len__(self) -> int:
        """Get number of songs in queue."""
        return len(self._queue)
    
    async def add(self, song: Song) -> int:
        """Add a song to the queue.
        
        Args:
            song: Song to add
            
        Returns:
            Position in queue (1-indexed)
            
        Raises:
            QueueFullError: If queue is at maximum capacity
        """
        async with self._lock:
            if self.is_full():
                raise QueueFullError(self.max_size)
            
            self._queue.append(song)
            position = len(self._queue)
            
            logger.info(
                f"Added '{song.title}' to queue for guild {self.guild_id} "
                f"at position {position}"
            )
            
            return position
    
    async def next(self) -> Optional[Song]:
        """Get the next song from the queue.
        
        Handles loop modes:
        - SONG: Returns current song again
        - QUEUE: Moves current to end and returns next
        - OFF: Returns next song
        
        Returns:
            Next song or None if queue is empty
        """
        async with self._lock:
            # Handle loop modes
            if self._loop_mode == LoopMode.SONG and self._current:
                logger.debug(f"Looping song: {self._current.title}")
                return self._current
            
            if self._loop_mode == LoopMode.QUEUE and self._current:
                # Add current to end of queue
                self._queue.append(self._current)
            
            # Get next song
            if self._queue:
                self._current = self._queue.popleft()
                logger.info(f"Next song for guild {self.guild_id}: {self._current.title}")
                return self._current
            
            # Queue is empty
            self._current = None
            logger.debug(f"Queue empty for guild {self.guild_id}")
            return None
    
    async def skip(self) -> Optional[Song]:
        """Skip current song and get next.
        
        Returns:
            Next song or None if queue is empty
        """
        async with self._lock:
            # Don't re-add current song even in loop mode
            if self._queue:
                self._current = self._queue.popleft()
                logger.info(f"Skipped to: {self._current.title}")
                return self._current
            
            self._current = None
            logger.debug(f"No more songs in queue for guild {self.guild_id}")
            return None
    
    async def clear(self):
        """Clear all songs from the queue."""
        async with self._lock:
            count = len(self._queue)
            self._queue.clear()
            self._current = None
            logger.info(f"Cleared {count} songs from queue for guild {self.guild_id}")
    
    async def remove(self, index: int) -> Song:
        """Remove a song at a specific position.
        
        Args:
            index: Position in queue (0-indexed)
            
        Returns:
            Removed song
            
        Raises:
            QueueEmptyError: If queue is empty
            IndexError: If index is out of range
        """
        async with self._lock:
            if self.is_empty():
                raise QueueEmptyError()
            
            if index < 0 or index >= len(self._queue):
                raise IndexError(f"Index {index} out of range (queue size: {len(self._queue)})")
            
            # Convert deque to list for removal
            queue_list = list(self._queue)
            removed = queue_list.pop(index)
            self._queue = deque(queue_list, maxlen=self.max_size)
            
            logger.info(f"Removed '{removed.title}' from position {index}")
            return removed
    
    async def shuffle(self):
        """Shuffle the queue randomly."""
        import random
        
        async with self._lock:
            if len(self._queue) <= 1:
                return
            
            queue_list = list(self._queue)
            random.shuffle(queue_list)
            self._queue = deque(queue_list, maxlen=self.max_size)
            
            logger.info(f"Shuffled queue for guild {self.guild_id}")
    
    def set_loop_mode(self, mode: LoopMode):
        """Set the loop mode.
        
        Args:
            mode: New loop mode
        """
        self._loop_mode = mode
        logger.info(f"Set loop mode to {mode.name} for guild {self.guild_id}")
    
    def get_queue_list(self) -> list[Song]:
        """Get a copy of the queue as a list.
        
        Returns:
            List of songs in queue order
        """
        return list(self._queue)
    
    def get_total_duration(self) -> int:
        """Calculate total duration of all queued songs.
        
        Returns:
            Total duration in seconds
        """
        return sum(song.duration for song in self._queue if song.duration > 0)


class QueueManager:
    """Manages music queues for all guilds.
    
    This singleton class provides centralized access to per-guild queues,
    handling creation and cleanup automatically.
    """
    
    _instance: Optional[QueueManager] = None
    
    def __new__(cls):
        """Ensure only one QueueManager instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._queues: Dict[int, GuildMusicQueue] = {}
            logger.info("Initialized QueueManager singleton")
        return cls._instance
    
    def get_queue(
        self,
        guild_id: int,
        *,
        max_size: Optional[int] = None,
        default_volume: Optional[float] = None
    ) -> GuildMusicQueue:
        """Get or create a queue for a guild.
        
        Args:
            guild_id: Discord guild ID
            max_size: Maximum queue size (used only for new queues)
            
        Returns:
            GuildMusicQueue for the specified guild
        """
        if guild_id not in self._queues:
            queue_max = max_size if max_size is not None else settings.music_max_queue_size
            volume_default = (
                default_volume
                if default_volume is not None
                else settings.music_default_volume
            )
            self._queues[guild_id] = GuildMusicQueue(
                guild_id,
                queue_max,
                volume_default,
            )
            logger.debug(f"Created new queue for guild {guild_id}")
        
        return self._queues[guild_id]
    
    def remove_queue(self, guild_id: int):
        """Remove a guild's queue.
        
        Args:
            guild_id: Discord guild ID
        """
        if guild_id in self._queues:
            del self._queues[guild_id]
            logger.info(f"Removed queue for guild {guild_id}")
    
    def clear_all(self):
        """Clear all guild queues."""
        count = len(self._queues)
        self._queues.clear()
        logger.info(f"Cleared all {count} guild queues")
