"""Voice audio handling using yt-dlp for music extraction.

This module provides the YTDLSource class for downloading and streaming
audio from YouTube and other supported platforms.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import discord
import yt_dlp

from utils.music_exceptions import NoResultsError, YTDLError

logger = logging.getLogger(__name__)

# Suppress yt-dlp's verbose output
# The lambda must accept **kwargs because yt-dlp sometimes passes arguments
yt_dlp.utils.bug_reports_message = lambda **kwargs: ''

# YTDL options for extracting audio information
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,  # Only download single song, not playlists
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',  # Search YouTube if not a URL
    'source_address': '0.0.0.0',  # Bind to IPv4
    'extract_flat': False,
}

# FFmpeg options for audio processing
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn -b:a 128k',  # No video, 128kbps audio bitrate
}


def _coerce_duration(value: Any) -> int:
    """Convert a raw duration value to a non-negative integer."""
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return 0
    return max(duration, 0)


def _normalize_info(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure extracted info has safe defaults for downstream consumers."""
    normalized = dict(data)
    normalized['duration'] = _coerce_duration(data.get('duration'))
    headers = data.get('http_headers') or {}
    if headers:
        normalized['http_headers'] = {str(k): str(v) for k, v in headers.items()}
    else:
        normalized['http_headers'] = None
    return normalized


def _build_before_options(headers: Optional[Dict[str, str]]) -> str:
    """Compose ffmpeg before_options including optional HTTP headers."""
    base = FFMPEG_OPTIONS['before_options']
    if not headers:
        return base
    header_lines = ''.join(f"{key}: {value}\r\n" for key, value in headers.items())
    safe_header_lines = header_lines.replace('"', '\\"')
    return f'{base} -headers "{safe_header_lines}"'


def _build_audio_source(stream_url: str, headers: Optional[Dict[str, str]]) -> discord.AudioSource:
    """Create an FFmpeg audio source handling reconnects and headers."""
    return discord.FFmpegPCMAudio(
        stream_url,
        before_options=_build_before_options(headers),
        options=FFMPEG_OPTIONS['options']
    )


class YTDLSource(discord.PCMVolumeTransformer):
    """Audio source for playing music from YouTube and other platforms.

    This class uses yt-dlp to extract audio streams and Discord.py's
    PCMVolumeTransformer for volume control.
    """

    def __init__(
        self,
        source: discord.AudioSource,
        *,
        data: Dict[str, Any],
        volume: float = 0.5
    ):
        super().__init__(source, volume)
        self.data = data
        self.title: str = data.get('title', 'Unknown')
        self.url: str = data.get('url', '')
        self.webpage_url: str = data.get('webpage_url', '')
        self.duration: int = _coerce_duration(data.get('duration'))
        self.thumbnail: Optional[str] = data.get('thumbnail')
        self.uploader: Optional[str] = data.get('uploader')
        self.view_count: Optional[int] = data.get('view_count')
        self.http_headers: Optional[Dict[str, str]] = data.get('http_headers')

    @classmethod
    async def create_source(
        cls,
        query: str,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        volume: float = 0.5
    ) -> YTDLSource:
        """Create an audio source from a search query or URL.

        Args:
            query: YouTube URL or search query
            loop: Event loop to use for async operations
            volume: Initial volume (0.0 to 1.0)

        Returns:
            YTDLSource ready for playback

        Raises:
            YTDLError: If extraction fails
            NoResultsError: If search returns no results
        """
        loop = loop or asyncio.get_event_loop()

        try:
            data = dict(await cls.get_info(query, loop=loop))

            if not data:
                raise NoResultsError(query)

            # Create the audio source
            filename = data.get('url')
            if not filename:
                raise YTDLError("Could not extract audio URL")

            data['url'] = filename
            source = _build_audio_source(filename, data.get('http_headers'))
            return cls(source, data=data, volume=volume)

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp download error for query '{query}': {e}")
            raise YTDLError(f"Failed to extract audio: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating source for '{query}': {e}", exc_info=True)
            raise YTDLError(f"Unexpected error: {str(e)}")

    @classmethod
    def from_stream(
        cls,
        stream_url: str,
        *,
        data: Dict[str, Any],
        volume: float = 0.5
    ) -> "YTDLSource":
        """Construct a source directly from a known audio stream URL."""
        source = _build_audio_source(stream_url, data.get('http_headers'))
        return cls(source, data=data, volume=volume)

    @staticmethod
    async def get_info(
        query: str,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        download: bool = False
    ) -> Dict[str, Any]:
        """Extract information from a URL or search query.

        Args:
            query: YouTube URL or search query
            loop: Event loop to use
            download: Whether to download the audio file

        Returns:
            Dictionary containing video information

        Raises:
            YTDLError: If extraction fails
        """
        loop = loop or asyncio.get_event_loop()
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

        try:
            # Run yt-dlp in executor to avoid blocking
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(query, download=download)
            )

            # If it's a search result, get the first video
            if 'entries' in data:
                data = data['entries'][0] if data['entries'] else None

            if not data:
                raise NoResultsError(query)

            logger.info(
                f"Extracted info for '{data.get('title', 'Unknown')}' "
                f"(duration: {data.get('duration', 0)}s)"
            )

            return _normalize_info(data)

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"yt-dlp extraction error for '{query}': {e}")
            raise YTDLError(f"Failed to extract info: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error extracting info for '{query}': {e}")
            raise YTDLError(f"Unexpected error: {str(e)}")

    @staticmethod
    async def get_playlist_info(
        url: str,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        max_songs: int = 50
    ) -> list[Dict[str, Any]]:
        """Extract information from a playlist URL.

        Args:
            url: YouTube playlist URL
            loop: Event loop to use
            max_songs: Maximum number of songs to extract

        Returns:
            List of video information dictionaries

        Raises:
            YTDLError: If extraction fails
        """
        loop = loop or asyncio.get_event_loop()

        # Allow playlists for this specific call
        options = YTDL_OPTIONS.copy()
        options['noplaylist'] = False
        options['playlistend'] = max_songs

        ytdl = yt_dlp.YoutubeDL(options)

        try:
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(url, download=False)
            )

            if 'entries' not in data:
                # Single video, not a playlist
                return [_normalize_info(data)] if data else []

            entries = [entry for entry in data['entries'] if entry]
            logger.info(f"Extracted {len(entries)} songs from playlist")

            return [_normalize_info(entry) for entry in entries[:max_songs]]

        except Exception as e:
            logger.error(f"Error extracting playlist '{url}': {e}")
            raise YTDLError(f"Failed to extract playlist: {str(e)}")

    @staticmethod
    def format_duration(seconds: int) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        seconds = _coerce_duration(seconds)

        if seconds == 0:
            return "Unknown"

        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
