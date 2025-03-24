# cogs/voice/track.py
"""Track class for representing a song in the music queue."""

import discord
from datetime import datetime

class Track:
    """Represents a song in the music queue."""
    
    def __init__(self, source, requester: discord.Member = None):
        """
        Initialize a Track object.
        
        Args:
            source: The audio source data
            requester: The Discord member who requested the song
        """
        self.source = source  # Audio source
        self.requester = requester
        
        # Extract metadata from source
        self.title = source.data.get('title', 'Unknown title')
        self.url = source.data.get('webpage_url', 'Unknown URL')
        self.duration = self._parse_duration(source.data.get('duration'))
        self.thumbnail = source.data.get('thumbnail', 'https://via.placeholder.com/120')
        self.uploader = source.data.get('uploader', 'Unknown uploader')
        self.id = source.data.get('id', 'Unknown ID')
        self.platform = self._get_platform(source.data.get('extractor', ''))
        self.added_at = datetime.now()
    
    @staticmethod
    def _parse_duration(duration):
        """Convert duration in seconds to readable format."""
        if duration is None:
            return "LIVE"
        
        # Convert to integer to handle float durations from some platforms (like SoundCloud)
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            # If conversion fails, try to round the float
            try:
                duration = round(float(duration))
            except (ValueError, TypeError):
                return "UNKNOWN"
        
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
            
    @staticmethod
    def _get_platform(extractor):
        """Get the platform name from the extractor."""
        if 'youtube' in extractor:
            return 'YouTube'
        elif 'soundcloud' in extractor:
            return 'SoundCloud'
        elif 'spotify' in extractor:
            return 'Spotify'
        else:
            return extractor.capitalize()
            
    def to_embed(self, embed_type="queue"):
        """
        Convert track to a Discord embed.
        
        Args:
            embed_type: Type of embed ("queue", "now_playing", or "added")
        
        Returns:
            discord.Embed: Formatted embed with track information
        """
        if embed_type == "now_playing":
            title = "Now Playing"
            color = discord.Color.green()
        elif embed_type == "added":
            title = "Added to Queue"
            color = discord.Color.blue()
        else:  # Queue item
            title = "Queued Track"
            color = discord.Color.blue()
            
        embed = discord.Embed(
            title=title,
            description=f"[{self.title}]({self.url})",
            color=color
        )
        embed.set_thumbnail(url=self.thumbnail)
        embed.add_field(name="Duration", value=self.duration, inline=True)
        embed.add_field(name="Requested by", value=self.requester.mention if self.requester else "Unknown", inline=True)
        embed.add_field(name="Platform", value=self.platform, inline=True)
        
        if self.uploader:
            embed.add_field(name="Uploader", value=self.uploader, inline=True)
            
        return embed