# xdBot Repository Agent Guide

This file replaces prior project markdown notes with one current, execution-focused reference.

## What This Repository Is

`xdBot` is a modular Discord bot built with `discord.py` and a cog-per-feature architecture.

Core capabilities:
- Discord hybrid commands (prefix + slash) across multiple cogs
- Async SQLite persistence with automatic schema checks/migrations
- Optional LLM responses (Ollama and/or OpenRouter) with tool calling and Tavily search support
- Music playback (voice join/playback/queue basics) via `yt-dlp`, `PyNaCl`, and FFmpeg
- Stock market commands and technical indicators via Polygon.io
- Misc utility/fun/admin/moderation/reply features

Main entrypoint: `main.py`

## Current Runtime Model

- Bot startup:
  - `main.py` builds `DiscordBot`, enables intents (`message_content`, `members`, `voice_states`), auto-loads all cogs in `cogs/` that expose `async def setup`.
  - App command tree sync runs in `setup_hook`.
- Cog loading:
  - Dynamic discovery by AST parse; only modules with async `setup` are loaded.
  - Currently detected cogs with setup:
    - `cogs/admin.py`
    - `cogs/fun.py`
    - `cogs/general.py`
    - `cogs/image.py`
    - `cogs/llm.py`
    - `cogs/moderation.py`
    - `cogs/music.py`
    - `cogs/replies.py`
    - `cogs/stocks.py`
- Shutdown:
  - Graceful SIGINT/SIGTERM handling and bot close in `main.py`.

## Configuration

Centralized in `config.py` via dataclass `Settings` and environment variables (`python-dotenv` loaded if present).

Important env vars:
- Required for bot runtime:
  - `DISCORD_TOKEN`
- Core:
  - `BOT_PREFIX` (default `!`)
  - `OWNER_IDS` (comma-separated Discord IDs)
  - `GUILD_ID` (optional)
- LLM:
  - `OLLAMA_URL`
  - `OLLAMA_CHAT_MODEL`
  - `OLLAMA_MENTION_MODEL`
  - `OPENROUTER_API_KEY`
  - `OPENROUTER_BASE_URL`
  - `OPENROUTER_SITE_URL`
  - `OPENROUTER_APP_NAME`
  - `OPENROUTER_DEFAULT_MODEL`
  - `TAVILY_API_KEY`
- Randomness:
  - `RANDOM_ORG_KEY`
- Stocks:
  - `POLYGON_API_KEY`

Current note from code:
- `config.py` default `OLLAMA_URL` is `http://192.168.50.69:11434`.

Music settings are currently in `Settings` with defaults:
- `music_max_queue_size=100`
- `music_idle_timeout=300`
- `music_default_volume=0.5`
- `music_max_duration=3600`

## Data Layer

Database handler: `utils/db_handler.py`
- Uses `aiosqlite` for async operations.
- Initializes DB at `data/bot.db`.
- Ensures/migrates core tables (users, command usage/cooldowns, word tracking, prompts, command executions, llm settings, music history).
- Applies indexes for common lookups.

## Feature Map (High-Level)

- LLM: `cogs/llm.py` + `utils/ollama_handler.py` + `utils/search_tool.py`
  - Provider abstraction, model config registration, per-guild model setting cache, mention handling, chunked response handling.
- Music: `cogs/music.py` + `utils/voice_handler.py` + `utils/music_queue.py` + `utils/music_exceptions.py`
  - Voice connect/move, play/pause/resume/skip/stop/volume, per-guild queue manager, idle auto-disconnect, play logging.
- Stocks: `cogs/stocks.py` + `utils/polygon_handler.py` + refactored support modules:
  - `utils/stock_service.py`
  - `utils/stock_models.py`
  - `utils/stock_embeds.py`
  - `utils/indicator_analyzer.py`
  - `utils/stock_tool.py`
  - `utils/chart_generator.py`

## Dependencies and Runtime Requirements

From `requirements.txt`:
- `discord.py`, `python-dotenv`, `aiohttp`, `aiosqlite`
- `numpy`, `matplotlib`
- `opencv-python-headless`, `mediapipe`
- `yt-dlp`, `PyNaCl`

System requirement for music:
- FFmpeg must be available in runtime environment.
- Included in `Dockerfile` install list.

Containerization:
- `Dockerfile`: Python 3.11 slim, installs FFmpeg + required system libs, then `pip install -r requirements.txt`, runs `python main.py`.
- `docker-compose.yml`: single service `discord-bot`, mounts repo into `/app`, injects `DISCORD_TOKEN`.

## Tests and Verification Artifacts

Repository includes focused scripts/tests:
- `test_music_setup.py` (pre-flight checks for music modules/deps/config/db)
- `test_chart_generation.py`
- `test_search_tool.py`
- `test_tool_selection.py`
- `test_voice_error.py`

These are useful smoke/regression entry points before deeper refactors.

## Practical Agent Workflow for This Repo

1. Environment prep:
- Create venv, install `requirements.txt`.
- Provide `.env` with at minimum `DISCORD_TOKEN`.
- Add optional keys based on target feature work.

2. Fast validation:
- `python -m compileall .`
- `python test_music_setup.py` (if touching voice/music)

3. Runtime validation:
- `python main.py`
- Confirm extension load logs and slash command sync.

4. Feature-scoped checks:
- Music: verify FFmpeg, voice permissions, queue progression.
- Stocks: verify `POLYGON_API_KEY` and endpoint availability.
- LLM: verify provider key/URL and model names.

## Known State Notes (Consolidated from Historical Docs + Code)

- Music feature received post-implementation bugfixes around:
  - yt-dlp lambda signature compatibility
  - FFmpeg parameter passing
  - async queue await/empty handling
  - cog cleanup behavior
  - stream URL freshness (prefer replay via `webpage_url` when needed)
- Stock subsystem has refactored service/model/analyzer/embed layers and includes a golden-cross detector path.
- Historical markdown files were progress logs; code should be treated as source of truth.

## Suggested Next Technical Hardening for Agentic Coding

- Add one canonical `make`/task runner entry for:
  - setup
  - lint/type check
  - test subsets
  - run
- Add CI for syntax + tests to reduce agent regression risk.
- Add `.env.example` reflecting actual `config.py` keys.
- Add test coverage for:
  - extension auto-discovery behavior
  - LLM model-key persistence paths
  - music queue transitions and idle disconnect timing

