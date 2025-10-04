# 🎵 Music Feature Setup Guide

This guide will help you set up and test the music playback feature for xdBot.

## Prerequisites

### 1. FFmpeg Installation (REQUIRED)

FFmpeg is required for audio processing. Install it based on your system:

#### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install ffmpeg
```

#### Windows:
1. Download from https://ffmpeg.org/download.html
2. Extract and add to PATH
3. Verify: `ffmpeg -version`

#### macOS:
```bash
brew install ffmpeg
```

#### Docker:
Already included in the Dockerfile (will be added).

### 2. Python Dependencies

Already added to `requirements.txt`:
- `yt-dlp>=2024.0.0` - YouTube video/audio extraction
- `PyNaCl>=1.5.0` - Voice encryption for Discord

Install with:
```bash
pip install -r requirements.txt
```

### 3. Discord Bot Permissions

Ensure your bot has these permissions in Discord:
- ✅ Connect (to join voice channels)
- ✅ Speak (to play audio)
- ✅ Use Voice Activity (for audio transmission)

**Permission Integer:** `36703232` (includes voice permissions)

## Configuration

### Environment Variables (Optional)

Add to your `.env` file (all have defaults):

```env
# Music settings (optional - defaults shown)
# MUSIC_MAX_QUEUE_SIZE=100
# MUSIC_IDLE_TIMEOUT=300
# MUSIC_DEFAULT_VOLUME=50
# MUSIC_MAX_DURATION=3600
```

## Testing Phase 2 - Core Commands

### Test Checklist

#### 1. Bot Startup Test
```bash
python main.py
```

Expected output:
```
✅ Loaded extension: cogs.music
🎵 Music cog loaded successfully
```

#### 2. Join Voice Channel Test

**In Discord:**
1. Join a voice channel
2. Run: `/join` or `!join`

**Expected:**
- ✅ Bot joins your voice channel
- ✅ Embed message: "🎵 Joined Voice Channel"

#### 3. Play a Song Test

**In Discord:**
```
/play never gonna give you up
```

**Expected:**
- ✅ Bot searches YouTube
- ✅ Bot starts playing audio
- ✅ Embed shows: "🎵 Now Playing" with song details
- ✅ Audio is audible in voice channel

#### 4. Queue Test

**Add multiple songs:**
```
/play darude sandstorm
/play nyan cat
/play ocean man
```

**Expected:**
- ✅ First song plays immediately
- ✅ Subsequent songs show "➕ Added to Queue" with position
- ✅ Songs auto-advance when current finishes

#### 5. Playback Control Tests

**Pause:**
```
/pause
```
✅ Audio pauses, embed confirms

**Resume:**
```
/resume
```
✅ Audio resumes, embed confirms

**Skip:**
```
/skip
```
✅ Current song skips, next song plays

**Volume:**
```
/volume 50
```
✅ Volume changes to 50%

**Stop:**
```
/stop
```
✅ Playback stops, queue clears

#### 6. Leave Test

```
/leave
```
✅ Bot disconnects from voice channel

#### 7. Multi-Guild Test

**In two different servers:**
1. Play different songs in each server
2. Verify independent queues
3. Commands in one server don't affect the other

#### 8. Auto-Disconnect Test

1. Let the queue finish completely
2. Wait 5 minutes (default idle timeout)
3. Bot should auto-disconnect

#### 9. Error Handling Tests

**User not in voice:**
```
/play test
```
✅ Error: "You must be in a voice channel"

**Different voice channels:**
1. Bot in Channel A
2. User in Channel B
3. Try `/skip`
✅ Error: "You must be in the same voice channel"

**Invalid volume:**
```
/volume 150
```
✅ Error: "Volume must be between 0 and 100"

## Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'yt_dlp'"
**Solution:**
```bash
pip install yt-dlp
```

### Issue: "FFmpeg not found"
**Solution:** Install FFmpeg (see Prerequisites section)

### Issue: "PyNaCl not installed"
**Solution:**
```bash
pip install PyNaCl
```

### Issue: Bot joins but no audio plays
**Checklist:**
1. FFmpeg installed? `ffmpeg -version`
2. Bot has "Speak" permission?
3. Check bot logs for errors
4. Try a different song

### Issue: "Age-restricted video" error
**Solution:** Use a different video/song. Age-restricted content requires authentication.

### Issue: Bot doesn't auto-disconnect
**Solution:** Check `MUSIC_IDLE_TIMEOUT` in config (default 300 seconds)

## Database Verification

Check if music history is being recorded:

```bash
sqlite3 data/bot.db "SELECT * FROM music_history LIMIT 5;"
```

Expected columns:
- id, guild_id, user_id, song_title, song_url, song_duration, played_at

## Phase 2 Completion Criteria

- ✅ All core commands work (join, leave, play, pause, resume, skip, stop, volume)
- ✅ Queue auto-advances
- ✅ Bot auto-disconnects on idle
- ✅ Multi-guild support works
- ✅ Error handling works correctly
- ✅ Database logging works
- ✅ No memory leaks (test with multiple songs)

## Next Steps

Once Phase 2 is complete and tested:
- **Phase 3:** Queue info commands (`nowplaying`, `queue`, etc.)
- **Phase 4:** Enhanced UX (loop modes, search selection)
- **Phase 5:** Statistics and polish

## Support Commands (for Debugging)

### Check if cog is loaded:
```
!sync
```

### Reload music cog (owner only):
```
!reload cogs.music
```

### Check bot logs:
```bash
tail -f logs/bot.log  # if logging to file
```

## Architecture Overview

```
User Command (/play song)
    ↓
cogs/music.py (Music cog)
    ↓
utils/voice_handler.py (YTDLSource - extract audio info)
    ↓
utils/music_queue.py (QueueManager - manage queue)
    ↓
Discord Voice Client (play audio)
    ↓
After callback → _play_next() → repeat
    ↓
utils/db_handler.py (log to music_history)
```

## Performance Notes

- **Memory:** ~50-100MB per active voice connection
- **CPU:** Minimal (streaming, not downloading full files)
- **Network:** ~128kbps per voice connection
- **Disk:** Temporary files cleaned automatically

## Security Notes

- ✅ No arbitrary code execution
- ✅ YTDL options restrict to audio only
- ✅ No playlist auto-expansion (Phase 2)
- ✅ Queue size limits prevent spam
- ✅ User must be in voice to control playback

---

**Phase 2 Status:** ✅ IMPLEMENTED
**Last Updated:** October 4, 2025
