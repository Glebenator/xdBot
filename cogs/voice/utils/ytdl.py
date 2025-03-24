# cogs/voice/utils/ytdl.py
"""Utilities for interacting with YouTube-DL."""

import discord
import yt_dlp as youtube_dl
import asyncio
import re
import logging
from .config import (
    YTDL_FORMAT_OPTIONS,
    YTDL_SEARCH_OPTIONS,
    FFMPEG_OPTIONS,
    URL_REGEX,
    YOUTUBE_REGEX,
    SPOTIFY_REGEX,
    SOUNDCLOUD_REGEX
)

# Setup logger
logger = logging.getLogger(__name__)

class YTDLSource:
    """Audio source from YouTube or other platforms using yt-dlp."""
    
    def __init__(self, source, *, data):
        """
        Initialize a YTDLSource.
        
        Args:
            source: Discord audio source
            data: Metadata from yt-dlp
        """
        self.source = source
        self.data = data
        
    @classmethod
    async def create_source(cls, search, *, loop=None, requester=None):
        """
        Create a source from a URL or search query.
        
        Args:
            search: URL or search query
            loop: Event loop
            requester: User who requested the song
            
        Returns:
            YTDLSource: Audio source with metadata
        """
        loop = loop or asyncio.get_event_loop()
        ytdl = youtube_dl.YoutubeDL(YTDL_FORMAT_OPTIONS)

        # Process the search query
        try:
            if re.match(URL_REGEX, search):  # If it's a URL
                # Handle Spotify separately
                if re.match(SPOTIFY_REGEX, search):
                    return await cls._handle_spotify(search, loop, requester)
                    
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=False))
                
                # Handle playlists
                if 'entries' in data:
                    # For playlists, return the first item
                    data = data['entries'][0]
            else:  # If it's a search query
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{search}", download=False))
                if 'entries' in data:
                    data = data['entries'][0]  # Take the first search result
                    
            filename = data['url']
            source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
            return cls(source, data=data)
            
        except Exception as e:
            logger.error(f"Error creating source: {e}")
            raise
            
    @classmethod
    async def _handle_spotify(cls, url, loop, requester):
        """
        Handle Spotify URLs by extracting info and searching on YouTube.
        
        Args:
            url: Spotify URL
            loop: Event loop
            requester: User who requested the song
            
        Returns:
            YTDLSource: Audio source with metadata
        """
        # Extract track/playlist name from Spotify URL and search on YouTube
        # This is a simple implementation - a real one would use Spotify API
        spotify_parts = url.split('/')
        search_query = spotify_parts[-1].split('?')[0]  # Extract ID
        query = f"spotify track {search_query}"
        
        # Search on YouTube
        return await cls.create_source(query, loop=loop, requester=requester)
            
    @classmethod
    async def search(cls, search_query, *, loop=None, limit=5):
        """
        Search for videos matching the query.
        
        Args:
            search_query: Search query
            loop: Event loop
            limit: Number of results to return
            
        Returns:
            list: List of search results
        """
        loop = loop or asyncio.get_event_loop()
        ytdl = youtube_dl.YoutubeDL(YTDL_SEARCH_OPTIONS)
        
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch{limit}:{search_query}", download=False))
            if 'entries' in data:
                return data['entries']
            return []
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return []
            
    @staticmethod
    def is_url(text):
        """Check if text is a URL."""
        return bool(re.match(URL_REGEX, text))
        
    @staticmethod
    def is_youtube(text):
        """Check if text is a YouTube URL."""
        return bool(re.match(YOUTUBE_REGEX, text))
        
    @staticmethod
    def is_spotify(text):
        """Check if text is a Spotify URL."""
        return bool(re.match(SPOTIFY_REGEX, text))
        
    @staticmethod
    def is_soundcloud(text):
        """Check if text is a SoundCloud URL."""
        return bool(re.match(SOUNDCLOUD_REGEX, text))