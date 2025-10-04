# 🐛 Bug Fix: FFmpeg Options & Stream URL

## Issue Encountered

When testing the `/play` command, encountered error:
```
❌ Search Failed
Could not find or load: https://www.youtube.com/watch?v=9bzuhxWZK00
Unexpected error: <lambda>() got an unexpected keyword argument 'before'
```

## Root Causes

### 1. FFmpeg Options Dictionary Unpacking ❌
**Problem:** Using `**FFMPEG_OPTIONS` to unpack the dictionary into FFmpegPCMAudio

```python
# WRONG - doesn't work
source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
```

**Why it failed:** `discord.FFmpegPCMAudio` doesn't accept arbitrary keyword arguments. The `before_options` and `options` parameters must be passed directly.

**Fix:** Pass parameters explicitly

```python
# CORRECT
source = discord.FFmpegPCMAudio(
    filename,
    before_options=FFMPEG_OPTIONS['before_options'],
    options=FFMPEG_OPTIONS['options']
)
```

### 2. Expired Stream URLs ⏰
**Problem:** YouTube stream URLs expire after a few hours

```python
# WRONG - stream URL expires
audio_source = await YTDLSource.create_source(
    song.url,  # This is the direct stream URL from initial extraction
    volume=queue.volume
)
```

**Why it failed:** The `song.url` contains the direct stream URL extracted when the song was added to the queue. If the song plays later (or is in queue), this URL will have expired.

**Fix:** Re-extract stream URL from webpage URL when playing

```python
# CORRECT - gets fresh stream URL
audio_source = await YTDLSource.create_source(
    song.webpage_url,  # YouTube watch URL (never expires)
    volume=queue.volume
)
```

## Files Modified

### 1. `utils/voice_handler.py`
**Line ~107:** Fixed FFmpegPCMAudio instantiation

```python
# Before
source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)

# After
source = discord.FFmpegPCMAudio(
    filename,
    before_options=FFMPEG_OPTIONS['before_options'],
    options=FFMPEG_OPTIONS['options']
)
```

### 2. `cogs/music.py`
**Line ~188:** Changed to use webpage_url for fresh extraction

```python
# Before
audio_source = await YTDLSource.create_source(
    song.url,
    volume=queue.volume
)

# After
audio_source = await YTDLSource.create_source(
    song.webpage_url,  # Use webpage_url to get fresh stream
    volume=queue.volume
)
```

## Why This Architecture is Better

### Song Dataclass Structure:
```python
@dataclass
class Song:
    title: str
    url: str              # Direct stream URL (expires)
    webpage_url: str      # YouTube watch URL (permanent)
    duration: int
    thumbnail: Optional[str]
    requester: discord.Member
    uploader: Optional[str] = None
```

### Usage Pattern:
1. **When adding to queue:** Extract `url` for metadata display
2. **When playing:** Re-extract from `webpage_url` for fresh stream

### Benefits:
- ✅ Handles expired URLs automatically
- ✅ Works for songs queued hours ago
- ✅ No "video unavailable" errors from stale URLs
- ✅ Minimal performance impact (extraction is async)

## Testing After Fix

Try these commands:

```
/play https://www.youtube.com/watch?v=9bzuhxWZK00
/play never gonna give you up
/play darude sandstorm
```

All should work without the "unexpected keyword argument" error.

## Additional Notes

### Stream URL Expiration
- YouTube stream URLs typically expire after 6 hours
- Always use `webpage_url` for playback
- Keep `url` for immediate playback optimization (Phase 4)

### FFmpeg Parameters
- `before_options`: Connection settings (reconnect, streaming)
- `options`: Output settings (audio only, no video)

### Error Handling
Both issues are now gracefully handled:
1. Invalid FFmpeg params → Fixed with explicit parameters
2. Expired URLs → Fixed by re-extracting on playback

## Verification

Run test script:
```bash
python test_music_setup.py
```

All checks should pass (except FFmpeg if not installed).

---

**Status:** ✅ Fixed  
**Date:** October 4, 2025  
**Impact:** Critical - Required for music playback to work
