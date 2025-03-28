# cogs/voice/track.py
import discord
from datetime import datetime

class Track:
    """Represents a song in the music queue."""

    def __init__(self, source_info, requester: discord.Member = None):
        """
        Initialize a Track object.

        Args:
            source_info: Dict containing 'source' (the FFmpeg audio) and 'data' (from YTDL)
            requester: The Discord member who requested the song
        """
        self.source = source_info['source'] # The FFmpegPCMAudio source object
        self.data = source_info['data'] # The dict from YTDL
        self.requester = requester

        # Extract metadata from data
        self.title = self.data.get('title', 'Unknown title')
        self.url = self.data.get('webpage_url', 'Unknown URL')
        self.duration_seconds = self.data.get('duration') # Duration in seconds (can be None)
        self.duration = self._parse_duration(self.duration_seconds) # Formatted duration string
        self.thumbnail = self.data.get('thumbnail', 'https://via.placeholder.com/120')
        self.uploader = self.data.get('uploader', 'Unknown uploader')
        self.id = self.data.get('id', 'Unknown ID')
        self.platform = self._get_platform(self.data.get('extractor', ''))
        self.added_at = datetime.now()

    @staticmethod
    def _parse_duration(duration_sec):
        """Convert duration in seconds to readable format M:SS or H:MM:SS."""
        if duration_sec is None:
            return "LIVE"

        try:
            # Ensure it's an integer for calculations
            duration_sec = int(round(float(duration_sec)))
            if duration_sec <= 0: return "0:00"
        except (ValueError, TypeError):
            return "Unknown"

        minutes, seconds = divmod(duration_sec, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _get_platform(extractor):
        """Get the platform name from the extractor."""
        if 'youtube' in extractor or 'ytsearch' in extractor:
            return 'YouTube'
        elif 'soundcloud' in extractor:
            return 'SoundCloud'
        elif 'spotify' in extractor: # Note: Spotify requires yt-dlp searching
            return 'Spotify (via YouTube)'
        else:
            return extractor.capitalize() if extractor else "Unknown"

    def to_embed(self, embed_type="queue"):
        """
        Convert track to a Discord embed.

        Args:
            embed_type: Type of embed ("queue", "now_playing", or "added")

        Returns:
            discord.Embed: Formatted embed with track information
        """
        if embed_type == "now_playing":
            title = "🎶 Now Playing"
            color = discord.Color.green()
        elif embed_type == "added":
            title = "✅ Added to Queue"
            color = discord.Color.blue()
        else:  # Queue item
            title = "📄 Queued Track"
            color = discord.Color.dark_gray()

        embed = discord.Embed(
            title=title,
            description=f"[{self.title}]({self.url})",
            color=color
        )
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)

        embed.add_field(name="Duration", value=self.duration, inline=True)
        embed.add_field(name="Requested by", value=self.requester.mention if self.requester else "Unknown", inline=True)
        embed.add_field(name="Platform", value=self.platform, inline=True)

        if self.uploader and self.platform != 'Spotify (via YouTube)': # Uploader is less relevant for Spotify searches
            embed.add_field(name="Uploader", value=self.uploader, inline=True)

        return embed