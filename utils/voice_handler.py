"""Resolve YouTube tracks and open verified HTTPS audio streams."""

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import discord
import yt_dlp

from config import settings
from utils.music_exceptions import MusicError

logger = logging.getLogger(__name__)
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
YTDL_OPTIONS = {
    "format": "bestaudio[protocol=https]/best[protocol=https]",
    "allowed_extractors": ["youtube", "youtube:search"],
    "noplaylist": True,
    "quiet": True,
    "socket_timeout": 10,
    "extractor_retries": 1,
    "retries": 1,
    "cachedir": False,
    "logger": logger,
}
EXTRACTORS = ThreadPoolExecutor(max_workers=3, thread_name_prefix="youtube")


@dataclass(frozen=True, slots=True)
class Track:
    video_id: str
    title: str
    duration: int

    @property
    def webpage_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def youtube_query(query: str) -> str:
    query = query.strip()
    if not 1 <= len(query) <= 300:
        raise MusicError("Enter a YouTube link or a search term of up to 300 characters.")
    if query.lower().startswith(tuple(f"{host}/" for host in YOUTUBE_HOSTS | {"youtu.be"})):
        query = f"https://{query}"
    try:
        parsed = urlsplit(query)
        if not parsed.scheme and not parsed.netloc:
            return f"ytsearch1:{query}"
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError
    except ValueError:
        raise MusicError("Enter a valid YouTube video link.") from None

    path = parsed.path.strip("/").split("/")
    video_id = ""
    if host == "youtu.be" and len(path) == 1:
        video_id = path[0]
    elif host in YOUTUBE_HOSTS:
        if path == ["watch"]:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif len(path) == 2 and path[0] in {"shorts", "live", "embed"}:
            video_id = path[1]
    if not VIDEO_ID.fullmatch(video_id):
        raise MusicError("Enter a YouTube video link or a plain search term.")
    return f"https://www.youtube.com/watch?v={video_id}"


def _extract(query: str) -> dict:
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as extractor:
        data = extractor.extract_info(query, download=False)
    if data and "entries" in data:
        data = next((entry for entry in data["entries"] if entry), None)
    if not data or not VIDEO_ID.fullmatch(str(data.get("id", ""))):
        raise MusicError("No YouTube video matched that request.")
    return data


async def _video_data(query: str) -> dict:
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(EXTRACTORS, _extract, youtube_query(query))
    except yt_dlp.utils.YoutubeDLError:
        logger.warning("YouTube could not resolve a video")
        raise MusicError("YouTube could not load that video.") from None


def _track(data: dict) -> Track:
    duration = int(data.get("duration") or 0)
    if data.get("is_live") or not 0 < duration <= settings.music_max_duration:
        raise MusicError(f"Choose a recorded video of up to {settings.music_max_duration} seconds.")
    return Track(data["id"], str(data.get("title") or "YouTube video"), duration)


async def resolve_track(query: str) -> Track:
    return _track(await _video_data(query))


async def open_audio(track: Track, volume: float) -> discord.PCMVolumeTransformer:
    data = await _video_data(track.webpage_url)
    _track(data)
    stream_url = data.get("url") or ""
    parsed = urlsplit(stream_url)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not host.endswith(".googlevideo.com") or parsed.username or parsed.password:
        raise MusicError("YouTube did not return a supported audio stream.")

    source = discord.FFmpegPCMAudio(
        stream_url,
        before_options=(
            "-nostdin -tls_verify 1 -rw_timeout 10000000 "
            "-protocol_whitelist https,tls,tcp -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
        ),
        options="-vn",
    )
    return discord.PCMVolumeTransformer(source, volume=volume)
