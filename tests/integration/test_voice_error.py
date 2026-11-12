"""Check YouTube extraction and FFmpeg audio with a real track."""

import pytest

from utils.voice_handler import open_audio, resolve_track


@pytest.mark.integration
@pytest.mark.asyncio
async def test_voice_source():
    track = await resolve_track("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    audio = await open_audio(track, 0.5)
    try:
        assert audio.read()
    finally:
        audio.cleanup()
