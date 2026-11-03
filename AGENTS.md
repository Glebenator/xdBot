# xdBot Repository Agent Guide

This is the execution-focused reference for agents. `README.md` is the user-facing guide; `.github/copilot-instructions.md` holds the coding conventions.

## What This Repository Is

`xdBot` is a modular Discord bot built with `discord.py` and a cog-per-feature architecture.

Core capabilities:
- Discord hybrid commands (prefix + slash) across multiple cogs
- Async SQLite persistence with automatic schema checks/migrations
- Optional LLM responses (Ollama and/or OpenRouter) with tool calling and web search (SearXNG first, Tavily as the fallback)
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
- `config.py` defaults `OLLAMA_URL` to `http://localhost:11434` and `SEARXNG_URL` to `http://localhost:8888`.
- `OLLAMA_MENTION_MODEL` falls back to `OLLAMA_CHAT_MODEL` when unset or empty.

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

`requirements.txt` pins exact versions that pass the suite on Python 3.11:
- `discord.py[voice]` (brings `PyNaCl` and `davey`; without `davey` voice is off), `python-dotenv`, `aiohttp`, `aiosqlite`
- `numpy`, `matplotlib`
- `opencv-python-headless`, `mediapipe` (held at 0.10.21: later releases dropped the FaceMesh solution that `cogs/image.py` uses)
- `yt-dlp`

Raise a pin on purpose and run `make check`.

System requirement for music:
- FFmpeg must be available in runtime environment.
- Included in `Dockerfile` install list.

Containerization:
- `Dockerfile`: two stages on Python 3.11 slim. The build stage installs `requirements.txt` into `/opt/venv` (gcc only here); the runtime stage adds FFmpeg, libGL and GLib, copies the venv, and runs `python main.py` as the unprivileged `bot` user (UID/GID 1000, build args `UID`/`GID`), which owns `data/`.
- `.dockerignore` keeps `.env`, local state in `data/`, tests and scripts out of the image.
- `docker-compose.yml`: single service `discord-bot`, `env_file: .env`, mounts only `./data`, and maps `host.docker.internal` to the Docker host.

## Tests and Verification Artifacts

- `tests/`: unit tests, run by `make test` and CI.
- `tests/integration/`: tests marked `integration` that need network access or API keys (chart generation, search, voice). Skipped by default; run with `pytest -m integration`.
- `scripts/check_music_setup.py`: pre-flight check of the music modules, dependencies, config and database.
- `scripts/demo_logging.py`: shows the LLM and search logging output.
- `scripts/tool_selection_demo.py`: sample queries for checking which tools the chat model picks.

## Practical Agent Workflow for This Repo

1. Environment prep:
- Create venv, install `requirements.txt`.
- For local quality tooling, also install `requirements-dev.txt`.
- Provide `.env` with at minimum `DISCORD_TOKEN`.
- Start from `.env.example`.
- Add optional keys based on target feature work.

2. Fast validation:
- `python -m compileall .`
- `python scripts/check_music_setup.py` (if touching voice/music)

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

## Current Quality Tooling

- `Makefile` commands:
  - `make install`
  - `make install-dev`
  - `make run`
  - `make compile`
  - `make lint`
  - `make test`
  - `make check`
- CI workflow: `.github/workflows/ci.yml`
  - compile check
  - ruff lint
  - pytest run

## Suggested Next Technical Hardening

- Add test coverage for:
  - extension auto-discovery behavior
  - LLM model-key persistence paths
  - music queue transitions and idle disconnect timing
