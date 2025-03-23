# utils/audio_constants.py
"""
Constants and configurations for audio processing
This module contains shared constants used by audio effects and music player modules
"""

# Default FFmpeg options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k'
}

# Specific FFmpeg options for livestreams
STREAM_FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        '-analyzeduration 12000000 -probesize 32000000'
    ),
    'options': (
        '-vn -b:a 160k '
        '-live_start_index -1 '  # Start from the latest segment
        '-fflags nobuffer '      # Reduce buffering
        '-flags low_delay '      # Minimize delay
        '-strict experimental'   # Allow experimental features
    )
}

# YT-DLP configuration
YTDLP_OPTIONS = {
    # Audio format selection
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio[ext=wav]/bestaudio/best',
    'prefer_free_formats': True,
    
    # Audio quality preferences
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'm4a',
        'preferredquality': '192',
    }],
    
    # Stream-specific settings
    'live_from_start': False,  # Start from current position for livestreams
    'wait_for_video': False,   # Don't wait for livestream to finish
    
    # Platform-specific settings
    'extract_flat': False,
    'writethumbnail': True,
    'no_playlist': True,
    
    # SoundCloud-specific settings
    'allow_playlist_files': False,
    'soundcloud_client_id': None,  # Will use internal client ID
    
    # Twitch-specific settings
    'twitch_disable_ads': True,    # Try to skip Twitch ads
    'twitch_skip_segments': True,
    
    # General settings
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    
    # Additional features
    'geo_bypass': True,
    'allow_unplayable_formats': False,
    'clean_infojson': False,
    'updatetime': False,
}

# Make sure to export all constants
__all__ = ['FFMPEG_OPTIONS', 'STREAM_FFMPEG_OPTIONS', 'YTDLP_OPTIONS']