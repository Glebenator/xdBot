"""Custom exceptions for music functionality.

This module defines music-specific exceptions that provide clear error
messages and help with graceful error handling throughout the music system.
"""

from discord.ext import commands


class MusicError(commands.CommandError):
    """Base exception for all music-related errors."""
    pass


class VoiceConnectionError(MusicError):
    """Raised when there's an issue connecting to a voice channel."""
    pass


class NotInVoiceChannelError(MusicError):
    """Raised when a user attempts a voice command while not in a voice channel."""

    def __init__(self, message: str = "You must be in a voice channel to use this command."):
        super().__init__(message)


class BotNotInVoiceError(MusicError):
    """Raised when a command requires the bot to be in voice but it isn't."""

    def __init__(self, message: str = "I'm not currently in a voice channel."):
        super().__init__(message)


class DifferentVoiceChannelError(MusicError):
    """Raised when user and bot are in different voice channels."""

    def __init__(self, message: str = "You must be in the same voice channel as me to use this command."):
        super().__init__(message)


class QueueFullError(MusicError):
    """Raised when attempting to add to a full queue."""

    def __init__(self, max_size: int):
        super().__init__(f"Queue is full! Maximum size is {max_size} songs.")
        self.max_size = max_size


class QueueEmptyError(MusicError):
    """Raised when attempting to perform operations on an empty queue."""

    def __init__(self, message: str = "The queue is empty."):
        super().__init__(message)


class YTDLError(MusicError):
    """Raised when yt-dlp encounters an error."""

    def __init__(self, message: str = "Error extracting audio information."):
        super().__init__(message)


class SongTooLongError(MusicError):
    """Raised when a song exceeds the maximum allowed duration."""

    def __init__(self, duration: int, max_duration: int):
        super().__init__(f"Song is too long ({duration}s). Maximum allowed is {max_duration}s.")
        self.duration = duration
        self.max_duration = max_duration


class NoResultsError(MusicError):
    """Raised when a search query returns no results."""

    def __init__(self, query: str):
        super().__init__(f"No results found for: {query}")
        self.query = query


class InvalidVolumeError(MusicError):
    """Raised when volume is set outside valid range."""

    def __init__(self, volume: int):
        super().__init__(f"Volume must be between 0 and 100. Got: {volume}")
        self.volume = volume
