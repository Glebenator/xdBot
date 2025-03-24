# utils/audio_constants.py
"""
Enhanced audio constants with optimized FFmpeg settings for high-quality audio playback in Discord
"""

# High-quality FFmpeg options for regular audio content
FFMPEG_OPTIONS = {
    'before_options': (
        # Connection stability options
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        # Extended analysis for better format detection
        '-analyzeduration 8000000 -probesize 25000000 '
    ),
    'options': (
        # Disable video processing
        '-vn '
        # High quality audio encoding
        '-b:a 256k '
        # Audio filters for quality and normalization
        '-af "aresample=resampler=soxr:precision=28:osf=s32:tsf=s32p:dither_method=triangular_hp:filter_size=128,dynaudnorm=f=150:g=15:p=0.7" '
        # Ensure consistent output format
        '-ac 2 -ar 48000 '
        # Performance optimizations
        '-threads 4 '
    )
}

# Optimized FFmpeg options for livestreams (balancing quality and latency)
STREAM_FFMPEG_OPTIONS = {
    'before_options': (
        # Connection stability with higher tolerance for streams
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 '
        # Extended buffer and analysis for streams
        '-analyzeduration 15000000 -probesize 35000000 '
        # Timeout settings for stream connections
        '-timeout 20000000 '
    ),
    'options': (
        # Disable video processing
        '-vn '
        # Good quality but lower than regular files to maintain stability
        '-b:a 192k '
        # Lighter audio filter for quality with less processing
        '-af "aresample=resampler=soxr:precision=20:osf=s16:filter_size=64,dynaudnorm=f=250:g=10" '
        # Ensure consistent output format
        '-ac 2 -ar 48000 '
        # Stream-specific options for reducing latency
        '-live_start_index -1 -fflags nobuffer -flags low_delay '
        # Allow experimental features for better stream handling
        '-strict experimental '
        # Reduce buffer size for lower latency
        '-max_muxing_queue_size 4096 '
        # Optimize for streams
        '-avioflags direct '
    )
}

# Platform-specific optimizations
PLATFORM_OPTIMIZATIONS = {
    'YouTube': {
        'format': 'bestaudio/best',
        'quality': 'highestaudio',
        'audio_options': '-b:a 256k -af "aresample=resampler=soxr:precision=28:dither_method=triangular_hp"'
    },
    'SoundCloud': {
        'format': 'bestaudio/best',
        'quality': 'highestaudio',
        'audio_options': '-b:a 256k -af "aresample=resampler=soxr:precision=28:dither_method=triangular_hp"'
    },
    'Twitch': {
        'format': 'audio_only/audio/best',
        'quality': 'highestaudio',
        'audio_options': '-b:a 192k -af "aresample=resampler=soxr" -live_start_index -1'
    },
    'Spotify': {
        'format': 'bestaudio/best',
        'quality': 'highestaudio',
        'audio_options': '-b:a 320k -af "aresample=resampler=soxr:precision=28:dither_method=triangular_hp"'
    },
    'Bandcamp': {
        'format': 'bestaudio/best',
        'quality': 'highestaudio',
        'audio_options': '-b:a 320k -af "aresample=resampler=soxr:precision=28:dither_method=triangular_hp"'
    }
}

# High-quality presets for specific audio enhancements
AUDIO_QUALITY_PRESETS = {
    'standard': '-af "aresample=resampler=soxr:precision=28:dither_method=triangular_hp"',
    'voice': '-af "aresample=resampler=soxr,highpass=f=200,lowpass=f=3000,dynaudnorm=g=5:p=0.9"',
    'music': '-af "aresample=resampler=soxr:precision=28,dynaudnorm=f=150:g=15:p=0.7"',
    'bass_boost': '-af "aresample=resampler=soxr,bass=g=5:f=110:w=0.6"',
}

# YT-DLP configuration optimized for high quality audio with improved YouTube compatibility
YTDLP_OPTIONS = {
    # Audio format selection - prioritize high quality formats but be flexible
    'format': 'bestaudio[acodec!=none]/bestaudio/best[acodec!=none]/best',
    'prefer_free_formats': True,
    
    # Audio quality preferences
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',  # Opus is excellent for voice and music
        'preferredquality': '256', # High quality
    }],
    
    # Stream-specific settings
    'live_from_start': False,
    'wait_for_video': False,
    
    # Platform-specific settings
    'extract_flat': False,
    'writethumbnail': True,
    'no_playlist': True,
    
    # SoundCloud-specific settings
    'allow_playlist_files': False,
    'soundcloud_client_id': None,
    
    # Twitch-specific settings
    'twitch_disable_ads': True,
    'twitch_skip_segments': True,
    
    # Advanced download settings
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
    
    # YouTube-specific optimizations
    'youtube_include_dash_manifest': False,  # Skip DASH manifests to improve speed
    'extractor_retries': 3,                  # Retry extraction on failure
    'fragment_retries': 10,                  # Increase fragment retry limit
    'skip_unavailable_fragments': True,      # Skip unavailable fragments
    'retry_sleep_functions': {'fragment': lambda n: 2.0 ** n},  # Exponential backoff
    
    # Concurrent downloads for better performance
    'concurrent_fragment_downloads': 3,
}
# Make sure to export all constants
__all__ = [
    'FFMPEG_OPTIONS', 
    'STREAM_FFMPEG_OPTIONS', 
    'PLATFORM_OPTIMIZATIONS',
    'AUDIO_QUALITY_PRESETS',
    'YTDLP_OPTIONS'
]