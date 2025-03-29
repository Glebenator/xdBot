# cogs/voice/utils/config.py
"""Configuration settings for the voice module."""

# URL validation patterns
URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»""'']))"
YOUTUBE_REGEX = r"^(https?\:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$"
SPOTIFY_REGEX = r"^(https?\:\/\/)?(open\.)?spotify\.com\/.+$"
SOUNDCLOUD_REGEX = r"^(https?\:\/\/)?(www\.)?(soundcloud\.com)\/.+$"

# YouTube DL options with high quality audio priority
YTDL_FORMAT_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'opus',  # Opus format for better quality
    'audioquality': '0',  # Highest quality
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # Allow playlists
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'preferredcodec': 'opus',  # Prefer Opus codec for high quality
    'postprocessor_args': ['-ar', '48000', '-ac', '2'],  # 48kHz sampling, 2 channels
}

# Options for flat extraction (search results, etc.)
YTDL_SEARCH_OPTIONS = {
    **YTDL_FORMAT_OPTIONS,
    'extract_flat': True,  # Do not extract video info
    'skip_download': True,
}

# FFmpeg options for audio playback
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -bufsize 3072k -ab 320k',  # Higher audio bitrate and buffer size
}

# Player settings
PLAYER_TIMEOUT = 180  # Seconds to wait for a new song before disconnecting
PLAYER_IDLE_TIMEOUT = 120  # Seconds to wait when alone in voice channel before disconnecting
MUSIC_INACTIVITY_TIMEOUT = 120
ALONE_TIMEOUT = 60