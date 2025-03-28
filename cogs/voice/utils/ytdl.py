# cogs/voice/utils/ytdl.py
import discord
import yt_dlp
import asyncio
import functools

# Silence useless bug reports messages
yt_dlp.utils.bug_reports_message = lambda: ''

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3', # You might prefer opus or others
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0', # Bind to ipv4 since ipv6 addresses cause issues sometimes.
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

class YTDLSource(discord.PCMVolumeTransformer):
    """Represents a YoutubeDL audio source."""

    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.duration = data.get('duration') # Duration in seconds
        self.uploader = data.get('uploader')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def _extract_data(cls, query, loop, download=False, process=True, seek_seconds=0):
        """Internal method to extract data using yt-dlp."""
        ydl_opts = YTDL_OPTIONS.copy()
        if not process:
            ydl_opts['extract_flat'] = 'discard_in_playlist'
            ydl_opts['lazy_extractors'] = True

        # Use functools.partial to run ydl in executor
        partial_extract = functools.partial(
            yt_dlp.YoutubeDL(ydl_opts).extract_info,
            query,
            download=download
        )
        data = await loop.run_in_executor(None, partial_extract)

        if data is None:
            raise yt_dlp.utils.DownloadError(f"Couldn't fetch data for {query}")

        # Handle playlists (taking the first item if query wasn't a direct link)
        if 'entries' in data:
             # If it's a playlist and the query wasn't a direct URL to an entry
            if not query.startswith(('http://', 'https://')) or 'playlist?list=' in query:
                 # Take the first item from the search results or playlist
                data = data['entries'][0]
            else:
                 # Find the specific entry if a direct playlist item URL was given
                entry_id = query.split('v=')[-1].split('&')[0]
                found_entry = next((entry for entry in data['entries'] if entry.get('id') == entry_id), None)
                if found_entry:
                    data = found_entry
                else: # Fallback to first if specific not found (shouldn't happen often)
                    data = data['entries'][0]


        # --- Add seek option to FFMPEG ---
        ffmpeg_options = FFMPEG_OPTIONS.copy()
        if seek_seconds > 0:
             ffmpeg_options['before_options'] += f' -ss {seek_seconds}'

        return data, ffmpeg_options

    @classmethod
    async def create_source(cls, query, *, loop=None, stream=True, requester=None, seek_seconds=0):
        """Creates a YTDLSource from a query (URL or search term)."""
        loop = loop or asyncio.get_event_loop()

        # Extract data and potentially modified ffmpeg options
        data, ffmpeg_options = await cls._extract_data(query, loop, download=not stream, process=True, seek_seconds=seek_seconds)

        if stream:
            source_url = data.get('url') # Direct stream URL
            if not source_url:
                 raise yt_dlp.utils.DownloadError("Could not extract stream URL.")
            # Return the raw source and data separately for Track creation
            return {
                'source': discord.FFmpegPCMAudio(source_url, **ffmpeg_options),
                'data': data
            }
        else:
            # Download is handled by _extract_data, filename is in data
            filename = yt_dlp.YoutubeDL(YTDL_OPTIONS).prepare_filename(data)
            return {
                'source': discord.FFmpegPCMAudio(filename, **ffmpeg_options),
                'data': data
            }

    @classmethod
    async def search(cls, query, *, loop=None, limit=5):
        """Searches youtube for videos."""
        loop = loop or asyncio.get_event_loop()
        ydl_opts = YTDL_OPTIONS.copy()
        ydl_opts['extract_flat'] = True # Don't extract full info yet
        ydl_opts['default_search'] = f"ytsearch{limit}" # Search youtube

        partial_extract = functools.partial(
            yt_dlp.YoutubeDL(ydl_opts).extract_info,
            query,
            download=False
        )
        results = await loop.run_in_executor(None, partial_extract)

        if not results or 'entries' not in results:
            return []

        # Return simplified entry data for selection
        return results['entries']