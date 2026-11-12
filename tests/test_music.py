import asyncio
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from cogs import music
from utils import voice_handler
from utils.music_exceptions import MusicError
from utils.voice_handler import Track, youtube_query

FIRST = Track("jNQXAC9IVRw", "First track", 30)
SECOND = Track("abcdefghijk", "Second track", 30)


@pytest.fixture
def session(monkeypatch):
    db = SimpleNamespace(log_music_play=AsyncMock())
    monkeypatch.setattr(music, "get_database_handler", lambda: db)
    cog = music.Music(SimpleNamespace(voice_clients=[]))
    channel = SimpleNamespace(mention="#voice")
    voice = SimpleNamespace(
        channel=channel,
        is_connected=lambda: True,
        is_playing=Mock(return_value=False),
        is_paused=Mock(return_value=False),
        stop=Mock(),
    )
    guild = SimpleNamespace(id=1, voice_client=voice)

    async def disconnect():
        guild.voice_client = None

    voice.disconnect = AsyncMock(side_effect=disconnect)
    channel.connect = AsyncMock(return_value=voice)
    channel.permissions_for = lambda _: SimpleNamespace(connect=True, speak=True)
    guild.me = object()
    ctx = SimpleNamespace(
        guild=guild,
        author=SimpleNamespace(id=10, voice=SimpleNamespace(channel=channel)),
        channel=SimpleNamespace(send=AsyncMock()),
        interaction=None,
        send=AsyncMock(),
    )
    return cog, cog._session(guild.id), voice, ctx


def test_youtube_short_link_and_search():
    assert youtube_query("https://youtu.be/jNQXAC9IVRw?t=1") == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert youtube_query("classic piano") == "ytsearch1:classic piano"


@pytest.mark.asyncio
async def test_one_worker_plays_tracks_in_queue_order(monkeypatch, session):
    cog, state, voice, ctx = session
    started = asyncio.Queue()
    logged = asyncio.Queue()
    cog.db.log_music_play.side_effect = lambda _, __, title, *args: logged.put_nowait(title)
    monkeypatch.setattr(music, "open_audio", AsyncMock(side_effect=lambda *args: SimpleNamespace()))
    voice.play = lambda source, *, after: started.put_nowait((source, after))
    state.pending.extend([
        music.QueuedTrack(FIRST, 10, ctx.channel),
        music.QueuedTrack(SECOND, 20, ctx.channel),
    ])

    await cog._start_worker(1, state, voice)
    worker = state.worker
    await cog._start_worker(1, state, voice)
    assert state.worker is worker
    try:
        first_audio, first_after = await asyncio.wait_for(started.get(), 1)
        assert len(state.pending) == 1
        cog.db.log_music_play.assert_not_awaited()
        await asyncio.to_thread(first_audio.on_first_frame)
        assert await asyncio.wait_for(logged.get(), 1) == FIRST.title
        await asyncio.to_thread(first_after, None)
        second_audio, second_after = await asyncio.wait_for(started.get(), 1)
        await asyncio.to_thread(second_audio.on_first_frame)
        assert await asyncio.wait_for(logged.get(), 1) == SECOND.title
        await asyncio.to_thread(second_after, None)
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["open", "read", "empty", "after_audio"])
async def test_track_failure_reaches_its_channel_and_queue_advances(monkeypatch, session, failure):
    cog, state, voice, ctx = session
    next_started = asyncio.Event()
    next_channel = SimpleNamespace(send=AsyncMock())
    state.pending.extend([
        music.QueuedTrack(FIRST, 10, ctx.channel),
        music.QueuedTrack(SECOND, 20, next_channel),
    ])

    async def open_audio(track, volume):
        if track == FIRST and failure == "open":
            raise ValueError("Unexpected source data")
        return SimpleNamespace(track=track)

    def play(source, *, after):
        if source.track == SECOND:
            next_started.set()
            return
        if failure == "after_audio":
            source.on_first_frame()
        after(None if failure == "empty" else OSError("FFmpeg read failed"))

    monkeypatch.setattr(music, "open_audio", open_audio)
    voice.play = play
    if failure == "open":
        ctx.channel.send.side_effect = OSError("The text channel is unavailable")
    await cog._start_worker(1, state, voice)
    try:
        await asyncio.wait_for(next_started.wait(), 1)
        ctx.channel.send.assert_awaited_once()
        assert FIRST.title in ctx.channel.send.await_args.args[0]
        next_channel.send.assert_not_awaited()
        assert cog.db.log_music_play.await_count == (1 if failure == "after_audio" else 0)
    finally:
        await cog.cog_unload()


def test_volume_wrapper_reports_ffmpeg_error_after_audio():
    class FailedSource(discord.AudioSource):
        def __init__(self):
            self.frame = b"\x00\x01" * 1920

        def read(self):
            if self.frame:
                frame, self.frame = self.frame, b""
                return frame
            self._current_error = OSError("FFmpeg exited with an error")
            return b""

    source = voice_handler.MusicAudio(FailedSource(), 0.5)
    started = Mock()
    source.on_first_frame = started
    assert len(source.read()) == 3840
    with pytest.raises(OSError, match="FFmpeg exited"):
        source.read()
    started.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["stop", "leave"])
@pytest.mark.parametrize("connected", [False, True])
async def test_clear_discards_search_results(monkeypatch, session, command, connected):
    cog, state, voice, ctx = session
    if not connected:
        ctx.guild.voice_client = None
    searching = asyncio.Event()
    release = asyncio.Event()

    async def resolve(query):
        searching.set()
        await release.wait()
        return FIRST

    monkeypatch.setattr(music, "resolve_track", resolve)
    request = asyncio.create_task(cog.play.callback(cog, ctx, query="test"))
    try:
        await asyncio.wait_for(searching.wait(), 1)
        if not connected:
            ctx.author.voice.channel = object()
            with pytest.raises(MusicError, match="pending music requests"):
                await getattr(cog, command).callback(cog, ctx)
            ctx.author.voice.channel = voice.channel
        await getattr(cog, command).callback(cog, ctx)
        release.set()
        with pytest.raises(MusicError, match="canceled"):
            await asyncio.wait_for(request, 1)
        assert not state.pending
        assert not state.searches
        voice.channel.connect.assert_not_awaited()
        assert voice.disconnect.await_count == (1 if connected and command == "leave" else 0)
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_skip_during_loading_starts_next_track(monkeypatch, session):
    cog, state, voice, ctx = session
    loading = asyncio.Event()
    canceled = asyncio.Event()
    next_started = asyncio.Event()
    state.pending.extend([music.QueuedTrack(track, 10, ctx.channel) for track in (FIRST, SECOND)])

    async def open_audio(track, volume):
        if track == FIRST:
            loading.set()
            try:
                await asyncio.Future()
            finally:
                canceled.set()
        return SimpleNamespace()

    monkeypatch.setattr(music, "open_audio", open_audio)
    voice.play = lambda source, *, after: next_started.set()
    await cog._start_worker(1, state, voice)
    try:
        await asyncio.wait_for(loading.wait(), 1)
        await cog.nowplaying.callback(cog, ctx)
        assert "**Loading**" in ctx.send.await_args.args[0]
        await cog.skip.callback(cog, ctx)
        assert canceled.is_set()
        await asyncio.wait_for(next_started.wait(), 1)
        assert state.current.item.track == SECOND
        ctx.channel.send.assert_not_awaited()
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_skip_after_source_starts_suppresses_playback_error(monkeypatch, session):
    cog, state, voice, ctx = session
    players = asyncio.Queue()
    monkeypatch.setattr(music, "open_audio", AsyncMock(side_effect=lambda *args: SimpleNamespace()))
    voice.play = lambda source, *, after: players.put_nowait(after)
    voice.is_playing.return_value = True
    state.pending.extend([music.QueuedTrack(track, 10, ctx.channel) for track in (FIRST, SECOND)])
    await cog._start_worker(1, state, voice)
    try:
        first_after = await asyncio.wait_for(players.get(), 1)
        voice.stop.side_effect = lambda: first_after(OSError("The stream closed during skip"))
        await cog.skip.callback(cog, ctx)
        await asyncio.wait_for(players.get(), 1)
        assert state.current.item.track == SECOND
        ctx.channel.send.assert_not_awaited()
        cog.db.log_music_play.assert_not_awaited()
    finally:
        await cog.cog_unload()


@pytest.mark.asyncio
async def test_queue_reserves_space_and_shows_positions(monkeypatch, session):
    cog, state, voice, ctx = session
    monkeypatch.setattr(music.settings, "music_max_queue_size", 6)
    monkeypatch.setattr(cog, "_start_worker", AsyncMock())
    resolve = AsyncMock(return_value=SECOND)
    monkeypatch.setattr(music, "resolve_track", resolve)
    state.current = music.CurrentTrack(music.QueuedTrack(FIRST, 10, ctx.channel), started=True)
    voice.is_paused.return_value = True
    state.pending.extend([music.QueuedTrack(SECOND, 20, ctx.channel)] * 5)
    state.searches[object()] = voice.channel
    with pytest.raises(MusicError, match="queue is full"):
        await cog.play.callback(cog, ctx, query="test")
    resolve.assert_not_awaited()
    state.searches.clear()

    await cog.play.callback(cog, ctx, query="test")
    assert "position 6" in ctx.send.await_args.args[0]
    await cog.queue.callback(cog, ctx)
    lines = ctx.send.await_args.args[0].splitlines()
    assert "**Paused**" in lines[0] and FIRST.title in lines[0]
    assert lines[1].startswith("1.") and lines[5].startswith("5.")
    assert lines[6] == "1 more in the queue."
    await cog.nowplaying.callback(cog, ctx)
    assert ctx.send.await_args.args[0] == lines[0]
    ctx.author.voice.channel = object()
    with pytest.raises(MusicError, match="bot's voice channel"):
        await cog.queue.callback(cog, ctx)


@pytest.mark.asyncio
async def test_idle_worker_disconnects(monkeypatch, session):
    cog, state, voice, ctx = session
    monkeypatch.setattr(music.settings, "music_idle_timeout", 0.01)
    await cog._start_worker(1, state, voice)
    await asyncio.wait_for(state.worker, 1)
    voice.disconnect.assert_awaited_once()
    assert ctx.guild.voice_client is None


@pytest.mark.asyncio
async def test_request_limit_reserves_an_extractor_for_playback(monkeypatch):
    release = Event()
    entered = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def extract(query):
        if query.startswith("ytsearch1:"):
            loop.call_soon_threadsafe(entered.put_nowait, query)
            assert release.wait(5)
        return {"id": FIRST.video_id, "title": FIRST.title, "duration": FIRST.duration}

    monkeypatch.setattr(voice_handler, "_extract", extract)
    requests = [asyncio.create_task(voice_handler.resolve_track(f"song {i}")) for i in range(2)]
    try:
        for _ in requests:
            await asyncio.wait_for(entered.get(), 1)
        requests[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await requests[0]
        with pytest.raises(MusicError, match="requests are busy"):
            await voice_handler.resolve_track("another song")
        playback = await asyncio.wait_for(voice_handler._video_data(FIRST.webpage_url), 1)
        assert playback["id"] == FIRST.video_id
    finally:
        release.set()
        await asyncio.gather(*requests, return_exceptions=True)
