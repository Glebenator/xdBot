import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs import music
from utils.voice_handler import Track, youtube_query


def test_youtube_short_link_and_search():
    assert youtube_query("https://youtu.be/jNQXAC9IVRw?t=1") == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert youtube_query("classic piano") == "ytsearch1:classic piano"


@pytest.mark.asyncio
async def test_one_worker_plays_tracks_in_queue_order(monkeypatch):
    started = asyncio.Queue()
    db = SimpleNamespace(log_music_play=AsyncMock())
    monkeypatch.setattr(music, "get_database_handler", lambda: db)
    monkeypatch.setattr(music, "open_audio", AsyncMock(return_value=SimpleNamespace(volume=0.5)))
    cog = music.Music(SimpleNamespace(voice_clients=[]))
    state = cog._session(1)

    def play(source, *, after):
        started.put_nowait(after)

    voice = SimpleNamespace(is_connected=lambda: True, play=play)
    state.pending.extend([
        (Track("jNQXAC9IVRw", "First track", 30), 10),
        (Track("abcdefghijk", "Second track", 30), 20),
    ])

    cog._start_worker(1, state, voice)
    worker = state.worker
    cog._start_worker(1, state, voice)
    assert state.worker is worker
    try:
        first_after = await asyncio.wait_for(started.get(), 1)
        assert len(state.pending) == 1
        await asyncio.to_thread(first_after, None)
        second_after = await asyncio.wait_for(started.get(), 1)
        await asyncio.to_thread(second_after, None)
        assert [call.args[2] for call in db.log_music_play.await_args_list] == [
            "First track",
            "Second track",
        ]
    finally:
        await cog.cog_unload()
